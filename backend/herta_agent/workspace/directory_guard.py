"""Pin Windows directory ancestors while accessing descendants by path."""

import os
from contextlib import contextmanager

from .paths import WorkspaceError, check_chain


@contextmanager
def directory_guard(path, *, writable_children=False):
    if os.name != "nt":
        check_chain(path)
        yield None
        return
    import ctypes
    from ctypes import wintypes

    class FileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("created", wintypes.FILETIME),
            ("accessed", wintypes.FILETIME),
            ("written", wintypes.FILETIME),
            ("volume", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
    api.GetFileInformationByHandle.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handles = []
    try:
        for part in reversed((path, *path.parents)):
            # OPEN_EXISTING + BACKUP_SEMANTICS + OPEN_REPARSE_POINT.
            # Read-only enumeration denies directory mutation. File jobs also
            # share writes for the native rename target lookup, bind leaf IO to
            # this handle, and still deny deletion/replacement of ancestors.
            share = 3 if writable_children else 1
            handle = api.CreateFileW(str(part), 0x80000000, share, None, 3, 0x02200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise WorkspaceError("目录不可访问或正在变化，请重试。")
            handles.append(handle)
            info = FileInformation()
            if not api.GetFileInformationByHandle(handle, ctypes.byref(info)):
                raise WorkspaceError("无法验证目录句柄。")
            if info.attributes & 0x400 or not info.attributes & 0x10:
                raise WorkspaceError("不读取符号链接或重解析点。")
        yield handles[-1]
    finally:
        for handle in reversed(handles):
            api.CloseHandle(handle)
