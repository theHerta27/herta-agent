"""Run pytest and parse structured JSON; the process backend owns cleanup."""

import asyncio
import json
from uuid import uuid4

from pydantic import Field

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.coding.sandbox import (
    CREATE_FLAGS,
    check_docker,
    cleanup_container,
    container_name,
    docker_command,
    docker_environment,
)
from herta_agent.tools.registry import ToolParameters, ToolSpec


def parse_report(report, exit_code):
    """Count complete test items, retaining structured stage/subtest evidence."""
    try:
        tests = report["tests"]
        summary = report["summary"]
        if (
            not isinstance(tests, list)
            or type(summary["total"]) is not int
            or summary["total"] != len(tests)
        ):
            raise ValueError
        if report["exitcode"] != exit_code:
            raise ValueError
        counts = dict(total=len(tests), passed=0, failed=0, skipped=0)
        seen = set()
        skipped_subtests = 0
        outcomes = {}
        for test in tests:
            if test["nodeid"] in seen:
                raise ValueError
            seen.add(test["nodeid"])
            outcome = test["outcome"]
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            evidence = [test[s] for s in ("setup", "call", "teardown") if s in test]
            evidence.extend(test.get("subtests", []))
            if outcome in {"passed", "skipped"} and any(e["outcome"] == "failed" for e in evidence):
                raise ValueError
            key = {
                "passed": "passed",
                "failed": "failed",
                "error": "failed",
                "skipped": "skipped",
                "xfailed": "skipped",
                "xpassed": "failed",
            }[outcome]
            counts[key] += 1
            skipped_subtests += sum(s["outcome"] == "skipped" for s in test.get("subtests", []))
        for outcome in {"passed", "failed", "error", "skipped", "xfailed", "xpassed"}:
            reported = summary.get(outcome, 0)
            if type(reported) is not int or reported != outcomes.get(outcome, 0):
                raise ValueError
        collectors = [c for c in report.get("collectors", []) if c["outcome"] == "failed"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolExecutionError(
            "test_report_invalid", "pytest JSON 报告缺失、损坏或不一致，未判定通过。"
        ) from exc
    if exit_code == 5 and not tests and not collectors:
        raise ToolExecutionError(
            "no_tests_collected", "pytest 未收集到测试，请检查 path 和 pattern。"
        )
    passed = exit_code == 0 and counts["total"] > 0 and counts["failed"] == 0 and not collectors
    return {
        "status": "passed" if passed else "failed",
        "exit_code": exit_code,
        **counts,
        "tests": tests,
        "collectors": collectors,
        "collection_errors": len(collectors),
        "skipped_subtests": skipped_subtests,
        "count_unit": "test_methods_or_functions",
        "runner": "pytest",
    }


class TestParameters(ToolParameters):
    path: str = Field(default="tests", min_length=1, max_length=1000)
    pattern: str = Field(default="test*.py", pattern=r"^test[a-zA-Z0-9_.*?-]*\.py$", max_length=100)


def run_tests(workspace, timeout=60):
    async def run(p):
        async with workspace.lock:
            start = workspace.path(p.path)
            if not start.is_dir():
                raise ToolExecutionError("not_directory", "测试入口必须是副本中的目录。")
            report = workspace.root / (".coding-test-" + uuid4().hex + ".json")
            docker, image = await check_docker()
            name = container_name()
            command = docker_command(
                docker, name, workspace, workspace.relative(start), p.pattern, report.name, image
            )
            process = None
            output = bytearray()
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=workspace.root,
                    env=docker_environment(),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=CREATE_FLAGS,
                )
                while block := await process.stdout.read(4096):
                    output.extend(block)
                    if len(output) > 64000:
                        raise ToolExecutionError(
                            "test_output_limit",
                            "测试输出超过 64KB，已停止；缩小测试范围后重试，未判定通过。",
                        )
                await process.wait()
                try:
                    if report.is_symlink() or not report.resolve().is_relative_to(workspace.root):
                        raise ToolExecutionError("test_report_invalid", "pytest 报告路径无效。")
                    if report.stat().st_size > 4 * 1024 * 1024:
                        raise ToolExecutionError(
                            "test_report_limit", "pytest 报告超过 4MB，请缩小范围。"
                        )
                    data = json.loads(report.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise ToolExecutionError(
                        "test_report_invalid", "pytest 未生成有效 JSON 报告。"
                    ) from exc
                return {
                    **parse_report(data, process.returncode),
                    "output": output.decode("utf-8", errors="replace"),
                    "isolation": "docker: nonroot, no network, limited resources, workspace mount",
                    "container_name": name,
                }
            finally:
                cleanup = asyncio.create_task(cleanup_container(docker, name, process))
                cancelled = False
                try:
                    # Timeout/Stop may arrive *during* cleanup, including a repeated Stop.
                    # Retain the workspace lock and ownership until the child is reaped.
                    while not cleanup.done():
                        try:
                            await asyncio.shield(cleanup)
                        except asyncio.CancelledError:
                            cancelled = True
                    cleanup.result()
                    if cancelled:
                        raise asyncio.CancelledError
                finally:
                    report.unlink(missing_ok=True)

    return ToolSpec(
        "run_tests",
        "在 Docker 沙箱挂载隔离副本执行 pytest；结果 status 才代表测试通过/失败，"
        "工具成功不等于测试通过。需要 Docker Desktop 和已构建的靶场镜像，无本地回退。",
        TestParameters,
        run,
        timeout=timeout,
    )
