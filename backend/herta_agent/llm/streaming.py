"""Bounded SSE framing and Chat Completions accumulation, without tool execution."""

import json
import re
from dataclasses import dataclass

from herta_agent.runtime.errors import ProviderProtocolError
from herta_agent.runtime.messages import Message, ModelReply, ToolCall

MAX_FRAME_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ReplyCompleted:
    reply: ModelReply


def _bad():
    return ProviderProtocolError("模型流式响应不完整或不符合受支持的协议；未保存为完整回答。")


async def sse_data(chunks):
    """Frame raw UTF-8 bytes before decoding; limits include ignored SSE fields."""
    buffer = b""
    data = []
    total = frame_size = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise _bad()
        buffer += chunk
        while match := re.search(b"[\r\n]", buffer):
            end = match.start()
            if buffer[end:] == b"\r":
                break  # CRLF may straddle network chunks.
            width = 2 if buffer[end : end + 2] == b"\r\n" else 1
            line, buffer = buffer[:end], buffer[end + width :]
            frame_size += end + width
            if frame_size > MAX_FRAME_BYTES:
                raise _bad()
            if not line:
                if data:
                    yield b"\n".join(data).decode("utf-8", errors="strict")
                data, frame_size = [], 0
            elif line == b"data" or line.startswith(b"data:"):
                value = line[5:] if line.startswith(b"data:") else b""
                data.append(value[1:] if value.startswith(b" ") else value)
        if frame_size + len(buffer) > MAX_FRAME_BYTES:
            raise _bad()
    # A final lone CR is a line separator too.
    if buffer == b"\r":
        if frame_size + 1 > MAX_FRAME_BYTES:
            raise _bad()
        if data:
            yield b"\n".join(data).decode("utf-8", errors="strict")
        data = []
        buffer = b""
    if buffer or data:
        raise _bad()


class _Reply:
    def __init__(self):
        self.text = []
        self.calls = {}
        self.finish = None
        self.done = False
        self.usage_seen = False

    def consume(self, data):
        if self.done:
            raise _bad()
        if data == "[DONE]":
            if self.finish is None:
                raise _bad()
            self.done = True
            return None
        value = json.loads(data)
        if not isinstance(value, dict) or "error" in value:
            raise _bad()
        choices = value.get("choices")
        if (
            choices == []
            and self.finish
            and isinstance(value.get("usage"), dict)
            and not self.usage_seen
        ):
            self.usage_seen = True
            return None
        if self.finish or not isinstance(choices, list) or len(choices) != 1:
            raise _bad()
        choice = choices[0]
        if (
            not isinstance(choice, dict)
            or type(choice.get("index")) is not int
            or choice["index"] != 0
        ):
            raise _bad()
        delta = choice.get("delta")
        if not isinstance(delta, dict) or delta.get("function_call") is not None:
            raise _bad()
        if delta.get("role") not in (None, "assistant"):
            raise _bad()
        text = delta.get("content")
        if text is not None:
            if not isinstance(text, str):
                raise _bad()
            self.text.append(text)
        fragments = delta.get("tool_calls")
        if fragments is not None:
            if not isinstance(fragments, list):
                raise _bad()
            for fragment in fragments:
                self._call(fragment)
        finish = choice.get("finish_reason")
        if finish is not None:
            if finish not in ("stop", "tool_calls"):
                raise _bad()
            self.finish = finish
        return text

    def _call(self, fragment):
        if not isinstance(fragment, dict):
            raise _bad()
        index = fragment.get("index")
        if type(index) is not int or not 0 <= index < 128:
            raise _bad()
        call = self.calls.setdefault(index, {"id": None, "type": None, "name": [], "arguments": []})
        for key in ("id", "type"):
            if key in fragment:
                value = fragment[key]
                if not isinstance(value, str) or (call[key] is not None and value != call[key]):
                    raise _bad()
                if key == "type" and value != "function":
                    raise _bad()
                call[key] = value
        function = fragment.get("function", {})
        if not isinstance(function, dict):
            raise _bad()
        for key in ("name", "arguments"):
            if key in function:
                if not isinstance(function[key], str):
                    raise _bad()
                call[key].append(function[key])

    def complete(self):
        if not self.done or (self.finish == "tool_calls") != bool(self.calls):
            raise _bad()
        if sorted(self.calls) != list(range(len(self.calls))):
            raise _bad()
        calls = []
        for _, call in sorted(self.calls.items()):
            if call["type"] != "function" or not call["arguments"]:
                raise _bad()
            calls.append(
                ToolCall(
                    id=call["id"], name="".join(call["name"]), arguments="".join(call["arguments"])
                )
            )
        return ModelReply(
            message=Message(
                role="assistant",
                content="".join(self.text) if self.text else None,
                tool_calls=tuple(calls),
            )
        )


async def parse_stream(chunks):
    reply = _Reply()
    try:
        async for data in sse_data(chunks):
            text = reply.consume(data)
            if text:
                yield TextDelta(text)
        # Check EOF too: trailing duplicate terminal frames cannot commit a reply.
        yield ReplyCompleted(reply.complete())
    except (ValueError, TypeError, UnicodeError):
        raise _bad() from None
