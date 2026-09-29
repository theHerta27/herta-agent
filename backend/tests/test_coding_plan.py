import unittest

from herta_agent.runtime.messages import ToolCall
from herta_agent.tools.coding.plan import propose_plan
from herta_agent.tools.executor import ToolExecutor
from herta_agent.tools.registry import ToolRegistry


class PlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_requires_titles_and_rationales(self):
        registry = ToolRegistry()
        registry.register(propose_plan())
        executor = ToolExecutor(registry)
        invalid = await executor.execute(
            ToolCall(id="a", name="propose_plan", arguments='{"steps":[{"title":"read"}]}')
        )
        self.assertEqual(invalid.error.code, "invalid_arguments")
        valid = await executor.execute(
            ToolCall(
                id="b",
                name="propose_plan",
                arguments='{"steps":[{"title":"read","rationale":"understand"},{"title":"test","rationale":"verify"}]}',
            )
        )
        self.assertTrue(valid.ok)
        self.assertEqual([s["title"] for s in valid.data["steps"]], ["read", "test"])
        self.assertNotIn("status", valid.data["steps"][0])
