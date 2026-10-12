"""Resume an owned Windows worker only after attaching its process-tree job."""

import ctypes
from ctypes import wintypes


def resume_process(pid):
    class ThreadEntry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("id", wintypes.DWORD),
            ("owner", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("delta", wintypes.LONG),
            ("flags", wintypes.DWORD),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
    kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
    kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenThread.restype = wintypes.HANDLE
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(4, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Cannot inspect owned worker thread")
    try:
        item = ThreadEntry()
        item.size = ctypes.sizeof(item)
        present = kernel.Thread32First(snapshot, ctypes.byref(item))
        while present:
            if item.owner == pid:
                thread = kernel.OpenThread(2, False, item.id)
                try:
                    if not thread or kernel.ResumeThread(thread) == 0xFFFFFFFF:
                        raise OSError("Cannot resume owned worker")
                    return
                finally:
                    if thread:
                        kernel.CloseHandle(thread)
            present = kernel.Thread32Next(snapshot, ctypes.byref(item))
        raise OSError("Owned worker thread is unavailable")
    finally:
        kernel.CloseHandle(snapshot)
