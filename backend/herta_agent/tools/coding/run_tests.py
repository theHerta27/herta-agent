"""Confirmed local unittest execution; owns its child tree, never invokes a shell."""

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.coding.paths import Repository
from herta_agent.tools.registry import ToolParameters, ToolSpec


class TestParameters(ToolParameters):
    path: str = Field(default="tests", min_length=1, max_length=1000)
    pattern: str = Field(default="test*.py", pattern=r"^test[a-zA-Z0-9_.*?-]*\.py$", max_length=100)


class TestReport(ToolParameters):
    status: Literal["passed", "failed", "no_tests", "skipped"]
    tests_run: int = Field(ge=0)
    successful_tests: int = Field(ge=0)
    failure_events: int = Field(ge=0)
    error_events: int = Field(ge=0)
    skipped: int = Field(ge=0)
    expected_failures: int = Field(ge=0)
    unexpected_successes: int = Field(ge=0)
    exit_code: int


def test_directory(repo: Repository, parameters: TestParameters) -> Path:
    if sys.platform != "win32":
        raise ToolExecutionError("unsupported_platform", "本版测试执行仅在Windows启用。")
    start = repo.path(parameters.path)
    if not start.is_dir():
        raise ToolExecutionError("not_directory", "测试入口必须是项目中的目录。")
    lexical = repo.root / parameters.path
    for part in (lexical, *lexical.parents):
        if part == repo.root:
            break
        if part.is_symlink() or part.is_junction():
            raise ToolExecutionError("path_denied", "测试入口不能经过链接或联接。")
    return start


def test_command(repo: Repository, parameters: TestParameters, report: Path) -> list[str]:
    start = test_directory(repo, parameters)
    return [
        sys.executable,
        "-I",
        "-B",
        "-X",
        "utf8",
        str(Path(__file__).with_name("test_worker.py")),
        str(repo.root),
        str(start),
        parameters.pattern,
        str(report),
    ]


def run_owned(repo: Repository, parameters: TestParameters, stop: threading.Event) -> dict:
    if stop.is_set():
        raise ToolExecutionError("test_cancelled", "本次测试已取消，未启动进程。")
    if sys.platform != "win32":
        raise ToolExecutionError("unsupported_platform", "本版测试执行仅在Windows启用。")
    output, overflow = bytearray(), threading.Event()
    process = job = reader = None
    with tempfile.TemporaryDirectory(prefix="herta-test-report-") as folder:
        report = Path(folder) / "result.json"
        command = test_command(repo, parameters, report)
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("HERTA_") and key != "DEEPSEEK_API_KEY"
        }
        try:
            process = subprocess.Popen(
                command,
                cwd=repo.root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=0x08000000 | 0x4,
            )
            # Existing helpers: job lifetime ownership, not a filesystem sandbox.
            from herta_agent.companion.worker_process import resume_process
            from herta_agent.documents.process import attach_job

            job = attach_job(process, memory_limit=0)
            if stop.is_set():
                raise ToolExecutionError("test_cancelled", "本次测试已取消。")
            resume_process(process.pid)

            def drain():
                while block := process.stdout.read(4096):
                    remaining = 24000 - len(output)
                    output.extend(block[:remaining])
                    if len(block) > remaining:
                        overflow.set()
                        break

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            while process.poll() is None and not overflow.is_set() and not stop.is_set():
                stop.wait(0.02)
        except OSError:
            raise ToolExecutionError("test_start_failed", "无法启动本机Python测试进程。") from None
        finally:
            if job:
                job[0].CloseHandle(job[1])  # KILL_ON_JOB_CLOSE includes descendants.
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
                if reader is not None:
                    reader.join()
                if process.stdout is not None:
                    process.stdout.close()
        if overflow.is_set():
            raise ToolExecutionError(
                "test_output_limit", "测试输出超过24KB，已停止；请缩小范围。未判定通过。"
            )
        try:
            if stop.is_set() or report.is_symlink() or report.stat().st_size > 8192:
                raise ValueError
            result = TestReport.model_validate_json(report.read_bytes())
            if result.exit_code != process.returncode:
                raise ValueError
        except (OSError, ValueError, ValidationError):
            raise ToolExecutionError(
                "test_report_invalid", "测试未生成有效报告，未判定通过。"
            ) from None
        return {
            **result.model_dump(),
            "output": output.decode("utf-8", errors="replace"),
            "runner": "unittest",
            "isolation": "none; current-user permissions",
        }


def run_tests(repo: Repository) -> ToolSpec:
    async def run(parameters: TestParameters):
        test_directory(repo, parameters)
        stop = threading.Event()
        worker = asyncio.create_task(asyncio.to_thread(run_owned, repo, parameters, stop))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            stop.set()
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not worker.cancelled():
                worker.exception()  # Reap the worker's error before propagating cancellation.
            raise
        finally:
            stop.set()

    return ToolSpec(
        "run_tests",
        "经确认在Windows所选项目执行Python unittest；可指定测试目录和test*.py模式。"
        "status区分passed/failed/no_tests/skipped，工具ok不代表测试通过。"
        "会执行项目代码，具有当前用户权限，不是沙箱。",
        TestParameters,
        run,
        permission="side_effect",
    )
