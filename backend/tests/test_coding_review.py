import json
import tempfile
import unittest
from pathlib import Path

from herta_agent.runtime.messages import ToolCall
from herta_agent.service.review_mode import review_registry
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.executor import ToolExecutor


class ReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_has_no_write_tools_and_requires_categories(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "code.py").write_text("value = 1\n", encoding="utf-8")
            registry = review_registry(Repository(Path(folder)))
            self.assertEqual(
                {d["function"]["name"] for d in registry.definitions()},
                {"read_file", "grep_code", "list_directory", "submit_review"},
            )
            executor = ToolExecutor(registry)
            invalid = await executor.execute(
                ToolCall(
                    id="a", name="submit_review", arguments='{"findings":[{"title":"problem"}]}'
                )
            )
            self.assertEqual(invalid.error.code, "invalid_arguments")
            clean = await executor.execute(
                ToolCall(id="b", name="submit_review", arguments='{"findings":[]}')
            )
            self.assertTrue(clean.ok)
            self.assertEqual(clean.data["findings"], [])
            findings = [
                {
                    "category": "bug",
                    "title": "边界",
                    "path": "code.py",
                    "start_line": 1,
                    "end_line": 1,
                    "explanation": "不符合输入约定",
                }
            ]
            valid = await executor.execute(
                ToolCall(id="c", name="submit_review", arguments=json.dumps({"findings": findings}))
            )
            self.assertTrue(valid.ok)
            self.assertEqual(valid.data["findings"], findings)
