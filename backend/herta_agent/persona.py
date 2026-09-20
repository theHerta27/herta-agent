"""Load an explicitly chosen local soul document; never fall back or reuse stale text."""

from dataclasses import dataclass
from pathlib import Path

from herta_agent.runtime.context import ContextSnapshot
from herta_agent.runtime.errors import ContextError


@dataclass(frozen=True)
class PersonaContextBuilder:
    path: Path

    def snapshot(self) -> ContextSnapshot:
        # Small local document, read synchronously once per Run. No template expansion.
        try:
            raw = self.path.read_bytes()
        except OSError:
            raise ContextError(
                f"无法读取人格文件：{self.path}；请修复后重试，未调用模型。"
            ) from None
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise ContextError(f"人格文件解析失败，必须使用 UTF-8：{self.path}") from None
        if "\x00" in text:
            raise ContextError(f"人格文件解析失败，包含 NUL 非文本内容：{self.path}")
        if not text.strip():
            raise ContextError(f"人格文件为空：{self.path}；请填写 soul.md 后重试。")
        return ContextSnapshot(text)
