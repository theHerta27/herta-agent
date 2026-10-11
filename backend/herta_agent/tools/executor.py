"""Validate, await with a deadline, and return a JSON envelope to the model."""

import asyncio
import json
import math
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.registry import ToolRegistry, ToolSpec


class ToolError(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    message: str


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    data: JsonValue = None
    error: ToolError | None = None

    @classmethod
    def failure(cls, code: str, message: str) -> "ToolResult":
        return cls(ok=False, error=ToolError(code=code, message=message))

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False)


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        timeout: float = 10.0,
        *,
        max_result_bytes: int = 64_000,
        tool_policy: Callable[[ToolSpec], bool] | None = None,
    ) -> None:
        if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 600:
            raise ValueError("Tool timeout must be finite and within (0, 600]")
        if (
            isinstance(max_result_bytes, bool)
            or not isinstance(max_result_bytes, int)
            or max_result_bytes <= 0
        ):
            raise ValueError("Tool result size limit must be a positive integer")
        self.registry, self.timeout = registry, timeout
        self.max_result_bytes = max_result_bytes
        self.tool_policy = tool_policy

    def _permitted(self, spec):
        return spec.permission == "read_only" or (
            self.tool_policy is not None and self.tool_policy(spec)
        )

    async def execute(
        self, call: ToolCall, *, on_started: Callable[[], Awaitable[None]] | None = None
    ) -> ToolResult:
        spec = self.registry.get(call.name)
        if spec is None:
            return ToolResult.failure("unknown_tool", "没有注册此工具，请使用提供的工具名称。")
        if not self._permitted(spec):
            return ToolResult.failure("permission_denied", "此工具有副作用，当前运行未授权执行。")
        try:
            parameters = spec.parameters.model_validate_json(call.arguments)
        except ValidationError:
            return ToolResult.failure(
                "invalid_arguments", "参数不符合工具 JSON schema，请检查字段和类型。"
            )
        if on_started is not None:
            await on_started()  # Infrastructure errors must not become tool failures.
        if not self._permitted(spec):
            return ToolResult.failure("permission_denied", "此工具有副作用，当前运行未授权执行。")
        try:
            async with asyncio.timeout(spec.timeout if spec.timeout is not None else self.timeout):
                data = await spec.handler(parameters)
            result = ToolResult(ok=True, data=data)
            encoded = result.to_json()  # Reject invalid/nonfinite output before history.
            if len(encoded.encode("utf-8")) > self.max_result_bytes:
                return ToolResult.failure("result_too_large", "工具结果超过允许的大小。")
            return result
        except TimeoutError:
            return ToolResult.failure("timeout", "工具执行超时。")
        except ToolExecutionError as exc:
            return ToolResult.failure(exc.code, str(exc))
        except Exception:
            # CancelledError inherits BaseException and deliberately propagates to Runtime.
            return ToolResult.failure("execution_error", "工具执行失败。")
