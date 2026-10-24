"""Check the owned task independently of the model's final answer."""

import argparse
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from prepare import DEMO_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="核查本次自建平均值任务，不调用模型")
    parser.add_argument("project", type=Path)
    root = parser.parse_args().project.resolve()
    marker = root / ".herta-demo"
    if not root.is_relative_to(DEMO_ROOT.resolve()) or not marker.is_file():
        parser.error("只检查prepare.py在.local/coding-demo中新建的演示项目。")
    if marker.read_text(encoding="utf-8") != "average-v1\n":
        from cases import check_case

        try:
            result = check_case(root)
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["passed"] else 1
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    suite = unittest.TestLoader().discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    spec = importlib.util.spec_from_file_location(
        "demo_metrics_check", root / "metrics.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        independent = all(
            module.average(values) == expected
            for values, expected in (
                ([], 0),
                ([2, 4, 6], 4),
                ([-4, 2], -1),
                ([1.5, 2.5], 2),
            )
        )
    except (ArithmeticError, AttributeError, TypeError, ValueError):
        independent = False
    passed = result.wasSuccessful() and result.testsRun >= 3 and independent
    print(
        json.dumps(
            {
                "passed": passed,
                "tests_run": result.testsRun,
                "tests_passed": result.wasSuccessful(),
                "independent_behavior_passed": independent,
                "model_called_by_checker": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
