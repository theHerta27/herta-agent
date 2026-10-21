"""Standalone stdlib unittest worker; invoked by absolute path in an isolated Python."""

import json
import sys
import unittest
from pathlib import Path


class CountingResult(unittest.TextTestResult):
    successful_tests = 0

    def addSuccess(self, test):
        self.successful_tests += 1
        super().addSuccess(test)


def main():
    root, start, pattern, report = sys.argv[1:]
    # Stdlib is already imported; project imports must not reuse stale .pyc files.
    sys.pycache_prefix = str(Path(report).parent / "pycache")
    # -I ignores ambient PYTHONPATH; explicitly support imports from this project
    # and the test directory's parent (e.g. repository/backend/tests).
    sys.path[:0] = [root, str(Path(start).parent)]
    suite = unittest.TestLoader().discover(start, pattern=pattern)
    result = unittest.TextTestRunner(
        stream=sys.stdout, verbosity=2, resultclass=CountingResult
    ).run(suite)
    if not result.wasSuccessful():
        status = "failed"  # Setup errors can occur before testsRun increments.
    elif result.skipped and result.successful_tests == 0:
        status = "skipped"
    elif result.testsRun == 0:
        status = "no_tests"
    else:
        status = "passed"
    exit_code = 5 if status == "no_tests" else 1 if status == "failed" else 0
    data = {
        "status": status,
        "tests_run": result.testsRun,
        "successful_tests": result.successful_tests,
        "failure_events": len(result.failures),
        "error_events": len(result.errors),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "exit_code": exit_code,
    }
    Path(report).write_text(json.dumps(data), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
