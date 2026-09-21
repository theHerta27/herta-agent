"""Offline byte-level HTTP fixtures, not a real-model quality evaluation."""

import asyncio
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

from herta_agent.config import ProviderSettings
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.llm.streaming import ReplyCompleted, TextDelta
from herta_agent.runtime.errors import ModelTimeoutError, ProviderError, ProviderProtocolError
from herta_agent.runtime.messages import Message


def frame(delta=None, finish=None):
    return (
        "data: "
        + json.dumps(
            {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]},
            ensure_ascii=False,
        )
        + "\r\n\r\n"
    ).encode()


DONE = b"data: [DONE]\n\n"
MESSAGES = (Message(role="user", content="hi"),)


class Bytes(httpx.AsyncByteStream):
    def __init__(self, chunks, gate=None):
        self.chunks, self.gate = chunks, gate
        self.closed = False

    async def __aiter__(self):
        for i, chunk in enumerate(self.chunks):
            if self.gate is not None and i == 1:
                await self.gate.wait()
            yield chunk

    async def aclose(self):
        self.closed = True


class StreamingProviderTests(unittest.IsolatedAsyncioTestCase):
    async def provider(self, stream, status=200):
        settings = ProviderSettings(
            base_url="https://stream.test/v1", model="fixture", api_key=uuid4().hex
        )
        self.requests = []

        def handle(request):
            self.requests.append(request)
            return httpx.Response(
                status, stream=stream, headers={"content-type": "text/event-stream"}
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.addAsyncCleanup(client.aclose)
        return OpenAICompatibleProvider(settings, client)

    async def test_unicode_byte_fragments_and_request_contract(self):
        raw = b": heartbeat\n\n" + frame({"role": "assistant"}) + frame({"content": "你好"})
        raw += frame({"content": "世界", "reasoning_content": "hidden"}) + frame(finish="stop")
        raw += b'data: {"choices":[],"usage":{"total_tokens":4}}\n\n' + DONE
        stream = Bytes([raw[i : i + 1] for i in range(len(raw))])
        provider = await self.provider(stream)
        events = [event async for event in provider.stream(MESSAGES, tools=({"type": "function"},))]
        self.assertEqual([e.text for e in events if isinstance(e, TextDelta)], ["你好", "世界"])
        self.assertEqual(events[-1].reply.message.content, "你好世界")
        self.assertEqual(sum(isinstance(e, ReplyCompleted) for e in events), 1)
        self.assertTrue(stream.closed)
        body = json.loads(self.requests[0].content)
        self.assertTrue(body["stream"])
        self.assertEqual(body["model"], "fixture")
        self.assertIn("tools", body)

    async def test_multiline_data_and_cr_only_frames(self):
        raw = (
            b'data: {"choices":\n'
            b'data: [{"index":0,"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\n' + DONE
        )
        for separator in (b"\n", b"\r\n", b"\r"):
            wire = raw.replace(b"\n", separator)
            provider = await self.provider(Bytes([wire[i : i + 1] for i in range(len(wire))]))
            events = [e async for e in provider.stream(MESSAGES)]
            self.assertEqual(events[-1].reply.message.content, "ok")

    async def test_delta_arrives_before_end_and_cancel_closes_response(self):
        gate = asyncio.Event()
        stream = Bytes([frame({"content": "partial"}), frame(finish="stop") + DONE], gate)
        provider = await self.provider(stream)
        events = provider.stream(MESSAGES)
        self.assertEqual(await anext(events), TextDelta("partial"))
        self.assertFalse(gate.is_set())
        waiting = asyncio.create_task(anext(events))
        await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.assertTrue(stream.closed)

    async def test_interleaved_tool_name_and_arguments_fragments(self):
        def call(index, **fields):
            return {"index": index, **fields}

        raw = frame(
            {
                "tool_calls": [
                    call(1, id="b", type="function", function={"name": "ec", "arguments": "{"}),
                    call(0, id="a", type="function", function={"name": "echo", "arguments": "{"}),
                ]
            }
        )
        raw += frame(
            {
                "tool_calls": [
                    call(0, function={"arguments": '"text":"甲"}'}),
                    call(1, function={"name": "ho", "arguments": '"text":"乙"}'}),
                ]
            }
        )
        raw += frame(finish="tool_calls") + DONE
        provider = await self.provider(Bytes([raw]))
        events = [e async for e in provider.stream(MESSAGES)]
        self.assertEqual(len(events), 1)
        calls = events[0].reply.message.tool_calls
        self.assertEqual([c.id for c in calls], ["a", "b"])
        self.assertEqual([c.name for c in calls], ["echo", "echo"])
        self.assertEqual(json.loads(calls[1].arguments), {"text": "乙"})

    async def test_invalid_stream_never_yields_completed(self):
        text = frame({"content": "all text already arrived"})
        tool = {
            "index": 0,
            "id": "a",
            "type": "function",
            "function": {"name": "echo", "arguments": "{}"},
        }
        invalid = [
            b"",
            text,
            text + DONE,
            text + frame(finish="stop"),
            text + frame(finish="length") + DONE,
            text + frame(finish="content_filter") + DONE,
            b"data: {broken}\n\n",
            text + frame(finish="stop") + DONE + DONE,
            text + frame(finish="stop") + frame(finish="stop") + DONE,
            frame({"function_call": {"name": "legacy"}}) + frame(finish="stop") + DONE,
            frame(finish="tool_calls") + DONE,
            frame({"tool_calls": [tool]})
            + frame({"tool_calls": [{"index": 0, "id": "conflict"}]})
            + frame(finish="tool_calls")
            + DONE,
            frame({"tool_calls": [{**tool, "type": "other"}]}) + frame(finish="tool_calls") + DONE,
            frame({"tool_calls": [{**tool, "index": True}]}) + frame(finish="tool_calls") + DONE,
            frame({"tool_calls": [tool, {**tool, "index": 1}]}) + frame(finish="tool_calls") + DONE,
            frame({"tool_calls": [{**tool, "function": {"name": "echo", "arguments": {}}}]})
            + frame(finish="tool_calls")
            + DONE,
            frame({"role": "user", "content": "bad"}) + frame(finish="stop") + DONE,
            b'data: {"choices":[]}\n\n' + DONE,
            b'data: {"choices":[{"index":1,"delta":{"content":"bad"},"finish_reason":"stop"}]}\n\n'
            + DONE,
            b"data: \xff\n\n",
            text + b"data: [DONE]",
        ]
        for raw in invalid:
            with self.subTest(raw=raw[:80]):
                stream = Bytes([raw])
                provider = await self.provider(stream)
                seen = []
                with self.assertRaises(ProviderProtocolError):
                    async for event in provider.stream(MESSAGES):
                        seen.append(event)
                self.assertFalse(any(isinstance(e, ReplyCompleted) for e in seen))
                self.assertTrue(stream.closed)

    async def test_size_limits_include_comments_and_total_response(self):
        raw = frame({"content": "ok"}) + frame(finish="stop") + DONE
        provider = await self.provider(Bytes([raw]))
        with patch("herta_agent.llm.streaming.MAX_RESPONSE_BYTES", len(raw)):
            self.assertIsInstance([e async for e in provider.stream(MESSAGES)][-1], ReplyCompleted)
        for chunks, field, limit in (
            ([b":" + b"x" * 200], "MAX_FRAME_BYTES", 100),
            ([raw], "MAX_RESPONSE_BYTES", len(raw) - 1),
        ):
            provider = await self.provider(Bytes(chunks))
            with (
                patch(f"herta_agent.llm.streaming.{field}", limit),
                self.assertRaises(ProviderProtocolError),
            ):
                _ = [e async for e in provider.stream(MESSAGES)]

    async def test_http_errors_are_safe_and_not_retried(self):
        for status in (301, 401, 403, 429, 500):
            secret = uuid4().hex
            stream = Bytes([secret.encode()])
            provider = await self.provider(stream, status)
            with self.assertRaises(ProviderError) as caught:
                _ = [e async for e in provider.stream(MESSAGES)]
            self.assertNotIn(secret, str(caught.exception))
            self.assertEqual(len(self.requests), 1)
            self.assertTrue(stream.closed)

    async def test_transport_timeout_closes_stream_and_has_safe_error(self):
        class Timeout(Bytes):
            async def __aiter__(self):
                yield frame({"content": "partial"})
                raise httpx.ReadTimeout("sensitive server text")

        stream = Timeout([])
        provider = await self.provider(stream)
        with self.assertRaises(ModelTimeoutError) as caught:
            _ = [e async for e in provider.stream(MESSAGES)]
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertTrue(stream.closed)
