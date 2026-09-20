import asyncio
import json
import unittest

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.echo import EchoParameters, echo, echo_registry
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry, ToolSpec


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_duplicate_and_success(self):
        registry = echo_registry()
        schema = registry.definitions()[0]["function"]["parameters"]
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("text", schema["required"])
        with self.assertRaises(ValueError):
            registry.register(ToolSpec("echo", "Echo", EchoParameters, echo))
        result = await ToolExecutor(registry).execute(
            ToolCall(id="a", name="echo", arguments='{"text":"你好"}')
        )
        self.assertEqual(
            json.loads(result.to_json()), {"ok": True, "data": {"text": "你好"}, "error": None}
        )

    async def test_bad_arguments_and_unknown_name_are_results(self):
        executor = ToolExecutor(echo_registry())
        for arguments in [
            "{",
            "[]",
            "{}",
            '{"text":3}',
            '{"text":"x","extra":1}',
            '{"text":"x","delay_seconds":"1"}',
            '{"text":"x","delay_seconds":NaN}',
        ]:
            with self.subTest(arguments=arguments):
                result = await executor.execute(ToolCall(id="a", name="echo", arguments=arguments))
                self.assertEqual(result.error.code, "invalid_arguments")
        result = await executor.execute(ToolCall(id="a", name="missing", arguments="{}"))
        self.assertEqual(result.error.code, "unknown_tool")

    async def test_timeout_cleans_handler_and_returns_safe_error(self):
        cleaned = asyncio.Event()

        async def wait(args):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        registry = ToolRegistry()
        registry.register(ToolSpec("wait", "Wait", EchoParameters, wait))
        result = await ToolExecutor(registry, timeout=0.02).execute(
            ToolCall(id="a", name="wait", arguments='{"text":"x"}')
        )
        self.assertEqual(result.error.code, "timeout")
        self.assertTrue(cleaned.is_set())

    async def test_exception_does_not_leak_and_cancel_propagates(self):
        async def fail(args):
            raise RuntimeError("private-key")

        registry = ToolRegistry()
        registry.register(ToolSpec("fail", "Fail", EchoParameters, fail))
        result = await ToolExecutor(registry).execute(
            ToolCall(id="a", name="fail", arguments='{"text":"x"}')
        )
        self.assertEqual(result.error.code, "execution_error")
        self.assertNotIn("private-key", result.to_json())
        started, cleaned = asyncio.Event(), asyncio.Event()

        async def wait(args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        registry.register(ToolSpec("wait", "Wait", EchoParameters, wait))
        task = asyncio.create_task(
            ToolExecutor(registry).execute(ToolCall(id="b", name="wait", arguments='{"text":"x"}'))
        )
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set())
