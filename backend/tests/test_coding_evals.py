import asyncio
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "evals/coding/run_debug_eval.py"


class CodingEvalTests(unittest.IsolatedAsyncioTestCase):
    async def test_debug_fixtures_fail_before_reference_fix_and_pass_after(self):
        script = SCRIPT
        self.assertTrue(script.exists(), "debug evaluation helper is required")
        spec = importlib.util.spec_from_file_location("debug_eval", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cases = list((script.parent / "bugs").iterdir())
        self.assertGreaterEqual(len(cases), 10)
        with tempfile.TemporaryDirectory() as folder:
            for case in cases:
                if not case.is_dir():
                    continue
                result = await asyncio.wait_for(module.verify_fixture(case, Path(folder)), 10)
                self.assertEqual(result["before"]["status"], "failed", case.name)
                self.assertEqual(result["after"]["status"], "passed", case.name)
                self.assertTrue(result["reference_only"])
