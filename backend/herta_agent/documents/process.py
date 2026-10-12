"""Own the parser and its subprocess tree until success, timeout or cancellation."""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes

from herta_agent.workspace.paths import WorkspaceError


def attach_job(process):
    if os.name != "nt":
        return None

    class Limits(ctypes.Structure):
        _fields_ = [("data", ctypes.c_byte * 144)]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    job = api.CreateJobObjectW(None, None)
    limits = Limits()
    # JOBOBJECT_EXTENDED_LIMIT_INFORMATION, x64 BasicLimitInformation.LimitFlags offset16.
    ctypes.c_uint32.from_buffer(limits, 16).value = 0x2000  # KILL_ON_JOB_CLOSE
    if (
        not job
        or not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        or not api.AssignProcessToJobObject(job, int(process._handle))
    ):
        if job:
            api.CloseHandle(job)
        raise WorkspaceError("无法拥有文档处理进程，请重试。")
    return api, job


def run_document(request, cancel=None):
    process = subprocess.Popen(
        [sys.executable, "-m", "herta_agent.documents.worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    job = None
    try:
        job = attach_job(process)
        payload = json.dumps(request).encode()
        deadline, first = time.monotonic() + 40, True
        while True:
            if (cancel and cancel.is_set()) or time.monotonic() > deadline:
                raise WorkspaceError("文档处理已停止或超过40秒。")
            try:
                output, _error = process.communicate(input=payload if first else None, timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                first = False
        if process.returncode or len(output) > 45 * 1024 * 1024:
            raise WorkspaceError("文档处理失败或输出过大。")
        result = json.loads(output)
        if not result["ok"]:
            raise WorkspaceError(result["error"])
        return result["result"]
    finally:
        if job:
            job[0].CloseHandle(job[1])
        if process.poll() is None:
            process.kill()
        process.communicate()
