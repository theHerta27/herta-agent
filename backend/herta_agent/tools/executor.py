"""Validate, await with a deadline, and return a JSON envelope to the model."""

import asyncio
import json
import math

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.registry import ToolRegistry


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
    def __init__(self, registry: ToolRegistry, timeout: float = 10.0) -> None:
        if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 600:
            raise ValueError("Tool timeout must be finite and within (0, 600]")
        self.registry, self.timeout = registry, timeout

    async def execute(self, call: ToolCall) -> ToolResult:
        spec = self.registry.get(call.name)
        if spec is None:
            return ToolResult.failure("unknown_tool", "没有注册此工具，请使用提供的工具名称。")
        try:
            parameters = spec.parameters.model_validate_json(call.arguments)
        except ValidationError:
            return ToolResult.failure(
                "invalid_arguments", "参数不符合工具 JSON schema，请检查字段和类型。"
            )
        try:
            async with asyncio.timeout(spec.timeout if spec.timeout is not None else self.timeout):
                data = await spec.handler(parameters)
            result = ToolResult(ok=True, data=data)
            result.to_json()  # Reject invalid/nonfinite output before it reaches history.
            return result
        except TimeoutError:
            return ToolResult.failure("timeout", "工具执行超时。")
        except ToolExecutionError as exc:
            return ToolResult.failure(exc.code, str(exc))
        except Exception:
            # CancelledError inherits BaseException and deliberately propagates to Runtime.
            return ToolResult.failure("execution_error", "工具执行失败。")
