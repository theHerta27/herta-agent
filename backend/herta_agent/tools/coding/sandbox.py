"""Owned Docker CLI lifecycle. No socket mount and no local test fallback."""

import asyncio
import hashlib
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from herta_agent.runtime.errors import ToolExecutionError
from herta_agent.tools.execution_context import tool_call_id

DEFAULT_IMAGE = "herta-coding-sandbox:local"
CREATE_FLAGS = 0x08000000 if os.name == "nt" else 0


def container_name():
    identity = hashlib.sha256(tool_call_id.get().encode()).hexdigest()[:12]
    return f"herta-{identity}-{uuid4().hex}"


def docker_environment():
    # CLI needs Desktop context under USERPROFILE; no model secrets are inherited.
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "APPDATA",
        "LOCALAPPDATA",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
    }
    return {k: v for k, v in os.environ.items() if k.upper() in allowed}


async def terminate(process):
    if process.returncode is None:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32/taskkill.exe"),
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=CREATE_FLAGS,
            )
            try:
                await asyncio.wait_for(killer.wait(), 5)
            except TimeoutError:
                killer.kill()
                await killer.wait()
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
    await process.wait()


async def docker_cli(docker, *args):
    process = await asyncio.create_subprocess_exec(
        docker,
        *args,
        env=docker_environment(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        creationflags=CREATE_FLAGS,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 5)
        return process.returncode, output.decode("utf-8", errors="replace").strip()
    finally:
        await terminate(process)


async def check_docker():
    docker = shutil.which("docker")
    if not docker:
        raise ToolExecutionError(
            "docker_unavailable",
            "需要安装并启动 Docker Desktop（Linux containers）。run_tests 不会回退到本地执行。",
        )
    image = os.environ.get("HERTA_CODING_SANDBOX_IMAGE", DEFAULT_IMAGE)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,200}", image):
        raise ToolExecutionError("sandbox_image_invalid", "沙箱镜像名称无效。")
    try:
        code, system = await docker_cli(docker, "info", "--format", "{{.OSType}}")
        if code != 0 or system != "linux":
            raise ToolExecutionError(
                "docker_unavailable", "请启动 Docker Desktop 并切换到 Linux containers。"
            )
        code, _ = await docker_cli(docker, "image", "inspect", image, "--format", "{{.Id}}")
        if code != 0:
            raise ToolExecutionError(
                "sandbox_image_missing",
                "请先运行 scripts/build-coding-sandbox-image.ps1 构建靶场沙箱镜像。",
            )
    except (OSError, TimeoutError) as exc:
        raise ToolExecutionError(
            "docker_unavailable", "Docker 不可用或响应超时，请检查 Docker Desktop。"
        ) from exc
    return docker, image


def docker_command(docker, name, workspace, path, pattern, report, image):
    # --mount has its own comma-separated grammar. Reject ambiguity, never expand it.
    if "," in str(workspace.root):
        raise ToolExecutionError(
            "sandbox_path_invalid", "Docker 挂载目录不能包含逗号，请更换靶场目录。"
        )
    return [
        docker,
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        name,
        "--network",
        "none",
        "--memory",
        "1g",
        "--memory-swap",
        "1g",
        "--cpus",
        "2",
        "--pids-limit",
        "128",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,size=128m",
        "--mount",
        f"type=bind,source={workspace.root},target=/workspace",
        "--workdir",
        "/workspace",
        image,
        "python",
        "-B",
        "-m",
        "pytest",
        path,
        "-q",
        "--tb=short",
        "-o",
        f"python_files={pattern}",
        "-p",
        "pytest_jsonreport.plugin",
        "-p",
        "herta_pytest_report",
        "-p",
        "no:cacheprovider",
        "--json-report",
        f"--json-report-file=/workspace/{report}",
        "--json-report-omit=keywords,log,warnings",
    ]


async def cleanup_container(docker, name, process):
    # Reap the client first so it cannot submit a late create request after cleanup.
    if process is not None:
        await terminate(process)
    try:
        await docker_cli(docker, "kill", name)  # Missing/already-exited is harmless.
        await docker_cli(docker, "rm", "--force", name)
        code, remaining = await docker_cli(
            docker, "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"
        )
        if code != 0 or remaining:
            raise ToolExecutionError(
                "sandbox_cleanup", f"无法确认容器已清理：{name}；请检查 Docker Desktop。"
            )
    except (OSError, TimeoutError) as exc:
        raise ToolExecutionError(
            "sandbox_cleanup", f"容器清理失败：{name}；请检查 Docker Desktop。"
        ) from exc
