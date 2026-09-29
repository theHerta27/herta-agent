"""Preserve pytest 9 subtest evidence in pytest-json-report 1.5 reports.

Loaded only by the test child. No test bodies or unittest internals are changed.
"""

import pytest

_subtests = {}
_stages = {}


def pytest_sessionstart(session):
    _subtests.clear()
    _stages.clear()


def pytest_runtest_logreport(report):
    if hasattr(report, "context"):
        _subtests.setdefault(report.nodeid, []).append(
            {
                "outcome": report.outcome,
                "context": str(report.context),
                "longrepr": report.longreprtext,
            }
        )
    else:
        _stages.setdefault(report.nodeid, []).append(report.outcome)


@pytest.hookimpl(optionalhook=True)
def pytest_json_modifyreport(json_report):
    for test in json_report.get("tests", []):
        nodeid = test["nodeid"]
        subs = _subtests.get(nodeid, [])
        test["subtests"] = subs
        if not subs:
            continue
        outcomes = _stages.get(nodeid, [])
        if "failed" in outcomes or any(s["outcome"] == "failed" for s in subs):
            test["outcome"] = "failed"
        elif "skipped" in outcomes:
            test["outcome"] = "skipped"
        else:
            test["outcome"] = "passed"
    summary = {"total": len(json_report.get("tests", []))}
    for test in json_report.get("tests", []):
        outcome = test["outcome"]
        summary[outcome] = summary.get(outcome, 0) + 1
    for key in ("collected", "deselected"):
        if key in json_report["summary"]:
            summary[key] = json_report["summary"][key]
    json_report["summary"] = summary
