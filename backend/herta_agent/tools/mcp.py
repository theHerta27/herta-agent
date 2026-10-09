"""Opt-in, allowlisted read-only MCP tools using the official stdio SDK.

Configuration authorizes launching the specified local executable. MCP annotations
are additional checks, never an authorization grant or an operating system sandbox.
SDK contexts are owned by a dedicated task so transport faults cannot cancel callers.
"""

import asyncio
import copy
import json
import logging
import os
import re
from collections.abc import AsyncIterator, Collection, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.registry import ToolParameters, ToolSpec

_NAME = re.compile(r"[a-zA-Z0-9_-]{1,64}")
_STARTUP_SECONDS = 10.0
_MAX_DISCOVERED_TOOLS = 64


class _SDKDiagnosticsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # SDK protocol validation exceptions can embed raw, untrusted server text.
        return "/mcp/" not in record.pathname.replace("\\", "/")


@contextmanager
def _quiet_sdk_diagnostics() -> Iterator[None]:
    policy = _SDKDiagnosticsFilter()
    loggers = (
        logging.getLogger(),
        logging.getLogger("mcp.client.stdio"),
        logging.getLogger("client"),
    )
    for logger in loggers:
        logger.addFilter(policy)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeFilter(policy)


class MCPAdapterError(ValueError):
    """Credential-free error suitable for disabling optional MCP at startup."""


class MCPServerConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    command: str = Field(min_length=1)
    args: list[str]
    allowed_tools: list[str] = Field(min_length=1, max_length=64)
    timeout: float = Field(default=10.0, gt=0, le=600, allow_inf_nan=False)

    @field_validator("command")
    @classmethod
    def explicit_executable(cls, value: str) -> str:
        if not Path(value).is_absolute() or not Path(value).is_file():
            raise ValueError("MCP requires an existing absolute executable path")
        return value

    @field_validator("allowed_tools")
    @classmethod
    def tool_names(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not _NAME.fullmatch(name) for name in value):
            raise ValueError("MCP tool allowlist contains invalid or duplicate names")
        return value


class MCPConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    servers: list[MCPServerConfig] = Field(min_length=1, max_length=1)


def load_mcp_config(path: str | Path) -> MCPConfig:
    try:
        return MCPConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise MCPAdapterError("MCP 配置无效，已禁用可选 MCP 工具。") from None


def _parameters(schema: dict) -> type[ToolParameters]:
    """Retain the advertised JSON Schema; enforce it before tool.started."""
    schema = copy.deepcopy(schema)
    # Match Herta's strict top-level argument boundary unless explicitly advertised.
    if not any(key in schema for key in ("$ref", "$dynamicRef", "allOf", "anyOf", "oneOf")):
        schema.setdefault("additionalProperties", False)
    try:
        if schema.get("type") != "object":
            raise ValueError("Only object tool arguments are supported")
        if len(json.dumps(schema, allow_nan=False).encode("utf-8")) > 64_000:
            raise ValueError("Schema too large")
        pending = [schema]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                for key in ("$ref", "$dynamicRef", "$recursiveRef"):
                    if key in value and (
                        not isinstance(value[key], str) or not value[key].startswith("#")
                    ):
                        raise ValueError("External schema references are not supported")
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        Draft202012Validator.check_schema(schema)
    except (ValueError, TypeError, SchemaError):
        raise MCPAdapterError("MCP 工具参数 schema 无效。") from None
    validator = Draft202012Validator(schema)

    class MCPParameters(ToolParameters):
        model_config = ConfigDict(strict=True, extra="allow", allow_inf_nan=False)
        __pydantic_extra__: dict[str, JsonValue]

        @model_validator(mode="before")
        @classmethod
        def schema_arguments(cls, value):
            try:
                json.dumps(value, allow_nan=False)
                validator.validate(value)
            except Exception:
                raise ValueError("Arguments do not conform to MCP tool schema") from None
            return value

        @classmethod
        def model_json_schema(cls, **kwargs):
            return copy.deepcopy(schema)

    return MCPParameters


async def _discover(session: ClientSession) -> list[types.Tool]:
    tools = []
    cursor = None
    seen_cursors = set()
    while True:
        page = await session.list_tools(cursor=cursor)
        tools.extend(page.tools)
        if len(tools) > _MAX_DISCOVERED_TOOLS:
            raise MCPAdapterError("MCP 工具数量超过上限。")
        cursor = page.nextCursor
        if cursor is None:
            return tools
        if cursor in seen_cursors:
            raise MCPAdapterError("MCP 工具发现分页无效。")
        seen_cursors.add(cursor)


@asynccontextmanager
async def _connection_scope(
    config: MCPConfig, *, reserved_names: Collection[str] = ()
) -> AsyncIterator[tuple[ToolSpec, ...]]:
    """Yield fully validated ToolSpecs while their SDK session remains open.

    Startup is atomic: no tools are yielded on discovery or permission failure.
    Local tool names win; callers pass their registry names as reserved_names.
    No process environment containing API credentials is forwarded, and server
    stderr is discarded so transport errors cannot expose arbitrary child logs.
    """
    server = config.servers[0]
    active = False
    yielded = False
    try:
        with _quiet_sdk_diagnostics(), open(os.devnull, "w", encoding="utf-8") as errlog:  # noqa: ASYNC230
            params = StdioServerParameters(command=server.command, args=server.args, env={})
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    async with asyncio.timeout(_STARTUP_SECONDS):
                        await session.initialize()
                        advertised = await _discover(session)
                    names = [tool.name for tool in advertised]
                    if len(set(names)) != len(names) or any(
                        not _NAME.fullmatch(name) for name in names
                    ):
                        raise MCPAdapterError("MCP 工具名称无效或重复。")
                    by_name = {tool.name: tool for tool in advertised}
                    specs = []
                    for name in server.allowed_tools:
                        if name not in by_name or name in reserved_names:
                            raise MCPAdapterError("MCP 白名单工具缺失或与本地工具冲突。")
                        tool = by_name[name]
                        if (
                            tool.annotations is None
                            or tool.annotations.readOnlyHint is not True
                            or tool.annotations.destructiveHint is True
                        ):
                            raise MCPAdapterError("MCP 白名单工具未声明只读。")
                        parameters = _parameters(tool.inputSchema)

                        async def invoke(arguments: ToolParameters, remote_name=name):
                            if not active:
                                raise ToolExecutionError("mcp_unavailable", "MCP 连接已关闭。")
                            try:
                                result = await session.call_tool(
                                    remote_name, arguments.model_dump()
                                )
                            except TimeoutError:
                                raise
                            except Exception:
                                raise ToolExecutionError(
                                    "mcp_unavailable", "MCP 工具连接不可用。"
                                ) from None
                            if result.isError:
                                raise ToolExecutionError("mcp_tool_error", "MCP 工具执行失败。")
                            if result.structuredContent is not None:
                                return result.structuredContent
                            if any(
                                not isinstance(block, types.TextContent) for block in result.content
                            ):
                                raise ToolExecutionError(
                                    "mcp_result_error", "MCP 工具返回了不支持的结果类型。"
                                )
                            return {"content": [block.text for block in result.content]}

                        specs.append(
                            ToolSpec(
                                name,
                                tool.description or "Read-only MCP tool.",
                                parameters,
                                invoke,
                                timeout=server.timeout,
                                permission="read_only",
                            )
                        )
                    active = True
                    yielded = True
                    try:
                        yield tuple(specs)
                    finally:
                        active = False
    except Exception:
        if yielded:
            raise  # Errors from the caller's body remain infrastructure failures.
        raise MCPAdapterError("MCP 连接或工具发现失败，已禁用可选 MCP 工具。") from None


async def _call_with_transport_boundary(
    spec: ToolSpec, arguments: ToolParameters, closed: asyncio.Event
) -> object:
    if closed.is_set():
        raise ToolExecutionError("mcp_unavailable", "MCP 工具连接不可用。")
    request = asyncio.create_task(spec.handler(arguments), name="herta-mcp-request")
    disconnected = asyncio.create_task(closed.wait(), name="herta-mcp-disconnected")
    try:
        await asyncio.wait((request, disconnected), return_when=asyncio.FIRST_COMPLETED)
        if closed.is_set():
            raise ToolExecutionError("mcp_unavailable", "MCP 工具连接不可用。")
        return await request
    finally:
        for task in (request, disconnected):
            if not task.done():
                task.cancel()
        await asyncio.gather(request, disconnected, return_exceptions=True)


@asynccontextmanager
async def connect_mcp_tools(
    config: MCPConfig, *, reserved_names: Collection[str] = ()
) -> AsyncIterator[tuple[ToolSpec, ...]]:
    """Yield tools behind an isolated SDK connection owner.

    Both SDK contexts enter/exit in the owner task. Its AnyIO cancellation scopes
    cannot enclose the application's lifespan task. Transport crashes close the
    boundary and fail pending/future calls; ordinary application work continues.
    """
    ready: asyncio.Future[tuple[ToolSpec, ...]] = asyncio.get_running_loop().create_future()
    stopping = asyncio.Event()
    closed = asyncio.Event()

    async def own_connection() -> None:
        try:
            async with _connection_scope(config, reserved_names=reserved_names) as specs:
                if not ready.done():
                    ready.set_result(specs)
                await stopping.wait()
        except (Exception, asyncio.CancelledError):
            # Consume SDK task-group/decoder faults here, outside the application's
            # task. Startup errors contain no transport bodies or exception text.
            if not ready.done():
                ready.set_exception(
                    MCPAdapterError("MCP 连接或工具发现失败，已禁用可选 MCP 工具。")
                )
        finally:
            closed.set()

    owner = asyncio.create_task(own_connection(), name="herta-mcp-connection")
    try:
        specs = await ready
        wrapped = []
        for spec in specs:

            async def invoke(arguments: ToolParameters, remote_spec=spec):
                return await _call_with_transport_boundary(remote_spec, arguments, closed)

            wrapped.append(replace(spec, handler=invoke))
        yield tuple(wrapped)
    finally:
        stopping.set()
        if ready.cancelled():
            owner.cancel()
        # Shield the owner so cancellation of the app cannot strand SDK cleanup.
        try:
            await asyncio.shield(owner)
        except asyncio.CancelledError:
            owner.cancel()
            await owner
            raise
