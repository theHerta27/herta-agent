"""Optional one-line progress from existing events; never a second history or execution log."""

import sys

from herta_agent.runtime.events import RuntimeEvent
from herta_agent.tools.permissions import terminal_text


def label(value) -> str:
    if not isinstance(value, str):
        return "?"
    text = terminal_text(value[:80]).replace("\n", "\\n").replace("\t", "\\t")
    return text + ("…" if len(value) > 80 else "")


class TerminalEventSink:
    def __init__(self, stream=None):
        self.stream = sys.stderr if stream is None else stream
        self.disabled = False

    async def emit(self, event: RuntimeEvent) -> None:
        if self.disabled:
            return
        payload = event.payload
        if event.type == "context.prepared":
            counts = [
                value if type(value) is int and value >= 0 else "?"
                for value in (
                    payload.get("estimated_input_tokens"),
                    payload.get("input_budget"),
                    payload.get("omitted_message_count"),
                )
            ]
            text = f"上下文：估算输入 {counts[0]}/{counts[1]} Token，省略 {counts[2]} 条历史消息"
        elif event.type == "llm.started":
            text = "请求 Provider"
        elif event.type == "tool.started":
            text = "开始工具 " + label(payload.get("name"))
        elif event.type in ("tool.completed", "tool.failed"):
            name = payload.get("name")
            result = payload.get("result")
            result = result if isinstance(result, dict) else {}
            text = "工具 " + label(name)
            if event.type == "tool.failed":
                error = result.get("error")
                code = error.get("code") if isinstance(error, dict) else None
                text += " 未完成（" + label(code) + "）"
            else:
                text += " 调用完成"
                if name == "run_tests":
                    data = result.get("data")
                    status = data.get("status") if isinstance(data, dict) else None
                    text += "；测试状态=" + label(status)
        else:
            return  # Never render model text/deltas, arguments or tool result bodies.
        try:
            print(f"[步骤{event.step}] {text}", file=self.stream, flush=True)
        except (OSError, ValueError):
            # A closed progress stream must not abort an otherwise valid tool operation.
            self.disabled = True
