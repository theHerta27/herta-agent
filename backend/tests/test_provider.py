import asyncio
import json
import unittest

import httpx

from herta_agent.config import ProviderSettings, RunSettings
from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import (
    ModelTimeoutError,
    ProviderError,
    ProviderProtocolError,
    ToolsNotAvailableError,
)
from herta_agent.runtime.messages import Message
from herta_agent.runtime.session import Session

SETTINGS = ProviderSettings(
    base_url="https://example.test/custom/v1", model="test-model", api_key="test-secret"
)
MESSAGES = (Message(role="user", content="你好"),)


def completion(content: str = "模型回答", finish_reason: str = "stop") -> dict:
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}
        ]
    }


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_contract_and_runtime_integration(self) -> None:
        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=completion())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            agent = Agent(OpenAICompatibleProvider(SETTINGS, client))
            session = Session()
            await agent.run(session, "first")
            result = await agent.run(session, "second")
        self.assertEqual(result.reply, "模型回答")
        self.assertEqual(len(requests), 2)
        request = requests[1]
        self.assertEqual(str(request.url), "https://example.test/custom/v1/chat/completions")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.headers["authorization"], "Bearer test-secret")
        body = json.loads(request.content)
        self.assertEqual(set(body), {"model", "messages", "stream"})
        self.assertFalse(body["stream"])
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(
            [m["role"] for m in body["messages"]], ["system", "user", "assistant", "user"]
        )

    async def test_optional_null_tool_calls_and_extra_metadata_are_accepted(self) -> None:
        body = completion()
        body["choices"][0]["message"]["tool_calls"] = None
        body["usage"] = {"total_tokens": 10}
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
        ) as client:
            reply = await OpenAICompatibleProvider(SETTINGS, client).complete(MESSAGES)
        self.assertEqual(reply.message.content, "模型回答")

    async def test_error_statuses_do_not_leak_body_or_retry(self) -> None:
        for status in [301, 401, 403, 429, 500]:
            with self.subTest(status=status):
                calls = []

                def handle(request: httpx.Request, recorded=calls, code=status) -> httpx.Response:
                    recorded.append(request)
                    return httpx.Response(
                        code,
                        text="test-secret private-user-input",
                        headers={"Location": "https://elsewhere.test"},
                    )

                async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                    with self.assertRaises(ProviderError) as caught:
                        await OpenAICompatibleProvider(SETTINGS, client).complete(MESSAGES)
                self.assertEqual(len(calls), 1)
                self.assertNotIn("test-secret", str(caught.exception))
                self.assertNotIn("private-user-input", str(caught.exception))

    async def test_malformed_or_incomplete_responses_are_rejected(self) -> None:
        bodies = [
            [],
            {},
            {"choices": []},
            completion(""),
            completion("  "),
            completion("partial", "length"),
            completion("filtered", "content_filter"),
            {
                "choices": [
                    {"message": {"role": "user", "content": "wrong"}, "finish_reason": "stop"}
                ]
            },
        ]
        for body in bodies:
            with self.subTest(body=body):
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda _, payload=body: httpx.Response(200, json=payload)
                    )
                ) as client:
                    session = Session()
                    with self.assertRaises(ProviderProtocolError):
                        await Agent(OpenAICompatibleProvider(SETTINGS, client)).run(
                            session, "hello"
                        )
                    self.assertEqual([m.role for m in session.history], ["user"])

    async def test_invalid_json_is_sanitized(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text="test-secret"))
        ) as client:
            with self.assertRaises(ProviderProtocolError) as caught:
                await OpenAICompatibleProvider(SETTINGS, client).complete(MESSAGES)
        self.assertNotIn("test-secret", str(caught.exception))

    async def test_tool_calls_are_explicitly_rejected_even_with_stop(self) -> None:
        for finish_reason in ["stop", "tool_calls"]:
            body = completion("I will call a tool", finish_reason)
            body["choices"][0]["message"]["tool_calls"] = [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": "{}"},
                }
            ]
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _, payload=body: httpx.Response(200, json=payload)
                )
            ) as client:
                with self.assertRaises(ToolsNotAvailableError):
                    await OpenAICompatibleProvider(SETTINGS, client).complete(MESSAGES)

    async def test_network_errors_are_mapped_without_exposing_exception_text(self) -> None:
        for network_error, expected in [
            (httpx.ConnectError, ProviderError),
            (httpx.ReadTimeout, ModelTimeoutError),
        ]:
            with self.subTest(error=network_error.__name__):

                def handle(request: httpx.Request, error_type=network_error) -> httpx.Response:
                    raise error_type("test-secret", request=request)

                async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                    with self.assertRaises(expected) as caught:
                        await OpenAICompatibleProvider(SETTINGS, client).complete(MESSAGES)
                self.assertNotIn("test-secret", str(caught.exception))

    async def test_runtime_deadline_cancels_pending_http_transport(self) -> None:
        cleaned = asyncio.Event()

        async def handle(request: httpx.Request) -> httpx.Response:
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
            raise AssertionError("unreachable")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            agent = Agent(
                OpenAICompatibleProvider(SETTINGS, client), RunSettings(request_timeout=0.02)
            )
            with self.assertRaises(ModelTimeoutError):
                await agent.run(Session(), "timeout")
        self.assertTrue(cleaned.is_set())
