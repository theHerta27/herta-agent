"""Owned demo copies and independent graders; these tests never call a model."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "coding-task"


class CodingCaseTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("herta_coding_cases", EXAMPLE / "cases.py")
        self.cases = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cases)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def prepare(self, name):
        return self.cases.prepare_case(name, demo_root=self.root)

    def grade(self, project):
        return self.cases.check_case(project, demo_root=self.root)

    def reference_checkout(self, project):
        # Explicit human reference solution, only to test the grader.
        cart = project / "shop" / "cart.py"
        cart.write_text(
            cart.read_text().replace('item["unit_cents"]', 'item["unit_cents"] * item["quantity"]'),
            encoding="utf-8",
        )
        checkout = project / "shop" / "checkout.py"
        checkout.write_text(
            checkout.read_text().replace("shipping_fee(gross)", "shipping_fee(gross - discount)"),
            encoding="utf-8",
        )

    def test_prepare_creates_distinct_copies_and_never_overwrites_first(self):
        first = self.prepare("checkout")
        (first / "sentinel.txt").write_text("keep", encoding="utf-8")
        second = self.prepare("checkout")
        self.assertNotEqual(first, second)
        self.assertEqual((first / "sentinel.txt").read_text(), "keep")
        self.assertTrue((second / "tests" / "test_checkout.py").is_file())

    def test_initial_bug_is_failed_and_reference_solution_is_independently_verified(self):
        project = self.prepare("checkout")
        before = self.grade(project)
        self.assertFalse(before["passed"])
        self.assertFalse(before["tests_passed"])
        self.assertTrue(before["original_tests_unchanged"])
        self.reference_checkout(project)
        after = self.grade(project)
        self.assertTrue(after["passed"], after)
        self.assertTrue(after["independent_behavior_passed"])
        self.assertGreaterEqual(after["tests_run"], 7)

    def test_modified_original_test_fails_grading_even_when_all_assertions_pass(self):
        project = self.prepare("checkout")
        self.reference_checkout(project)
        target = project / "tests" / "test_checkout.py"
        target.write_bytes(target.read_bytes() + b"\n# changed by model\n")
        result = self.grade(project)
        self.assertTrue(result["tests_passed"])
        self.assertTrue(result["independent_behavior_passed"])
        self.assertFalse(result["original_tests_unchanged"])
        self.assertFalse(result["passed"])

    def test_skipped_added_test_does_not_count_as_a_fully_passing_demo(self):
        project = self.prepare("checkout")
        self.reference_checkout(project)
        (project / "tests" / "test_skipped.py").write_text(
            "import unittest\nclass Missing(unittest.TestCase):\n"
            " @unittest.skip('not verified')\n def test_new_behavior(self):\n  pass\n",
            encoding="utf-8",
        )
        result = self.grade(project)
        self.assertTrue(result["independent_behavior_passed"])
        self.assertFalse(result["tests_passed"])
        self.assertFalse(result["passed"])

    def test_initial_feature_case_passes_old_tests_but_fails_new_contract(self):
        result = self.grade(self.prepare("wordcount"))
        self.assertTrue(result["tests_passed"], result)
        self.assertFalse(result["independent_behavior_passed"])
        self.assertFalse(result["passed"])

    def test_feature_grader_accepts_a_reference_implementation_and_added_tests(self):
        # Reference implementation to check that the new contract is attainable.
        project = self.prepare("wordcount")
        (project / "wordcount" / "json_output.py").write_text(
            "import json\ndef to_json(result):\n return json.dumps(result, ensure_ascii=False)\n",
            encoding="utf-8",
        )
        cli = project / "wordcount" / "cli.py"
        cli.write_text(
            cli.read_text(encoding="utf-8")
            .replace(
                "import argparse", "import argparse\nfrom wordcount.json_output import to_json"
            )
            .replace('choices=("text",)', 'choices=("text", "json")')
            .replace(
                "    result = summarize(args.text)",
                "    result = summarize(args.text)\n"
                '    if args.format == "json":\n        print(to_json(result))\n        return',
            ),
            encoding="utf-8",
        )
        (project / "tests" / "test_json_output.py").write_text(
            "import json, unittest\nfrom wordcount.json_output import to_json\n"
            "from wordcount.counts import summarize\nclass JsonTests(unittest.TestCase):\n"
            " def test_empty(self):\n  self.assertEqual(json.loads(to_json(summarize(''))), "
            "{'total': 0, 'unique': 0, 'counts': {}})\n"
            " def test_unicode(self):\n  self.assertEqual("
            "json.loads(to_json(summarize('黑塔 黑塔')))['counts'], {'黑塔': 2})\n",
            encoding="utf-8",
        )
        result = self.grade(project)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["tests_run"], 5)

    def test_unknown_case_and_unowned_directory_are_rejected(self):
        with self.assertRaises(ValueError):
            self.prepare("../../private")
        with self.assertRaises(ValueError):
            self.cases.check_case(self.root.parent, demo_root=self.root)


if __name__ == "__main__":
    unittest.main()
