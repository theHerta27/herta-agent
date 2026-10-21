import unittest

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.echo import EchoParameters
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry, ToolSpec


class ToolPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_authorization_uses_validated_arguments_and_only_approves_once(self):
        effects, approvals = [], []

        async def handler(parameters):
            effects.append(parameters.text)
            return {"written": parameters.text}

        async def authorize(spec, parameters):
            approvals.append(parameters.text)
            parameters.text = "authority copy mutation"
            return True

        registry = ToolRegistry()
        registry.register(
            ToolSpec("write", "Write", EchoParameters, handler, permission="side_effect")
        )
        executor = ToolExecutor(registry, authorize=authorize)
        invalid = await executor.execute(
            ToolCall(id="bad", name="write", arguments='{"text":false}')
        )
        self.assertEqual(invalid.error.code, "invalid_arguments")
        self.assertEqual(approvals, [])
        result = await executor.execute(
            ToolCall(id="ok", name="write", arguments='{"text":"original"}')
        )
        self.assertEqual(result.data, {"written": "original"})
        self.assertEqual(approvals, ["original"])
        self.assertEqual(effects, ["original"])

    async def test_authorization_errors_and_non_boolean_answers_fail_closed(self):
        effects = []

        async def handler(parameters):
            effects.append(parameters.text)
            return {}

        async def broken(spec, parameters):
            raise RuntimeError("private fixture detail")

        async def truthy(spec, parameters):
            return "yes"

        registry = ToolRegistry()
        registry.register(
            ToolSpec("write", "Write", EchoParameters, handler, permission="side_effect")
        )
        for authority, code in ((broken, "approval_failed"), (truthy, "permission_denied")):
            result = await ToolExecutor(registry, authorize=authority).execute(
                ToolCall(id="x", name="write", arguments='{"text":"x"}')
            )
            self.assertEqual(result.error.code, code)
            self.assertNotIn("private fixture detail", result.to_json())
        self.assertEqual(effects, [])
        with self.assertRaises(ValueError):
            ToolExecutor(registry, tool_policy=lambda spec: True, authorize=broken)

    async def test_side_effect_is_denied_before_started_or_handler(self):
        signals = []

        async def handler(args):
            signals.append("handler")
            return {"written": True}

        async def started():
            signals.append("started")

        registry = ToolRegistry()
        registry.register(
            ToolSpec("write", "Write", EchoParameters, handler, permission="side_effect")
        )
        result = await ToolExecutor(registry).execute(
            ToolCall(id="a", name="write", arguments='{"text":"x"}'), on_started=started
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "permission_denied")
        self.assertEqual(signals, [])

    async def test_large_output_is_rejected_without_partial_success(self):
        async def handler(args):
            return {"text": "界" * 100}

        registry = ToolRegistry()
        registry.register(ToolSpec("large", "Large", EchoParameters, handler))
        result = await ToolExecutor(registry, max_result_bytes=200).execute(
            ToolCall(id="a", name="large", arguments='{"text":"x"}')
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "result_too_large")
        self.assertIsNone(result.data)

    def test_permission_and_result_limit_are_validated(self):
        async def handler(args):
            return {}

        with self.assertRaises(ValueError):
            ToolSpec("bad", "Bad", EchoParameters, handler, permission="unknown")
        for limit in (True, 0, -1, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                ToolExecutor(ToolRegistry(), max_result_bytes=limit)
