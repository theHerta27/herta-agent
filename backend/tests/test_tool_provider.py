import json
import unittest

import httpx
from test_provider import SETTINGS, completion

from herta_agent.llm.openai_compatible import OpenAICompatibleProvider
from herta_agent.runtime.agent import Agent
from herta_agent.runtime.errors import ProviderProtocolError
from herta_agent.runtime.session import Session
from herta_agent.tools.echo import echo_registry


def tool_body(calls=None, reason="tool_calls"):
    return {
        "choices": [
            {
                "finish_reason": reason,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": calls
                    if calls is not None
                    else [
                        {
                            "id": "one",
                            "type": "function",
                            "function": {"name": "echo", "arguments": '{"text":"hello"}'},
                        }
                    ],
                },
            }
        ]
    }


class ToolProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_adapter_posts_schema_and_paired_results(self):
        requests = []

        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(
                200, json=tool_body() if len(requests) == 1 else completion("done")
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await Agent(
                OpenAICompatibleProvider(SETTINGS, client), registry=echo_registry()
            ).run(Session(), "echo hello")
        self.assertEqual(result.steps, 2)
        self.assertEqual(requests[0]["tools"][0]["function"]["name"], "echo")
        self.assertEqual(requests[1]["messages"][-2], tool_body()["choices"][0]["message"])
        feedback = requests[1]["messages"][-1]
        self.assertEqual(set(feedback), {"role", "content", "tool_call_id"})
        self.assertEqual(feedback["tool_call_id"], "one")
        self.assertEqual(json.loads(feedback["content"])["data"], {"text": "hello"})
        self.assertEqual(set(requests[0]["messages"][0]), {"role", "content"})

    async def test_broken_calls_never_enter_history(self):
        normal = tool_body()["choices"][0]["message"]["tool_calls"][0]
        legacy = completion("legacy")
        legacy["choices"][0]["message"]["function_call"] = {"name": "echo", "arguments": "{}"}
        bodies = [
            tool_body([normal, normal]),
            tool_body([{**normal, "id": " "}]),
            tool_body([{**normal, "type": "other"}]),
            tool_body([{**normal, "function": {"name": "echo", "arguments": {}}}]),
            tool_body([], "tool_calls"),
            tool_body(reason="length"),
            legacy,
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
                        await Agent(
                            OpenAICompatibleProvider(SETTINGS, client), registry=echo_registry()
                        ).run(session, "hello")
                    self.assertEqual([m.role for m in session.history], ["user"])
