"""Windows file handles bind verified bytes to rename/delete operations."""

import ctypes
import os
from contextlib import contextmanager
from ctypes import wintypes

from .paths import WorkspaceError


def api():
    if os.name != "nt":
        raise WorkspaceError("受控文件执行目前仅支持 Windows。")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    return kernel


def native_error():
    return WorkspaceError(
        f"文件被占用、权限不足或目标冲突（Windows错误{ctypes.get_last_error()}）。"
    )


def directory_identity(handle):
    class Information(ctypes.Structure):
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

    kernel = api()
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(Information)]
    info = Information()
    if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise native_error()
    if info.attributes & 0x400 or not info.attributes & 0x10:
        raise WorkspaceError("目录已成为链接，不能执行。")

    class FileId(ctypes.Structure):
        _fields_ = [("volume", ctypes.c_ulonglong), ("identifier", ctypes.c_ubyte * 16)]

    kernel.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    file_id = FileId()
    if not kernel.GetFileInformationByHandleEx(
        handle, 18, ctypes.byref(file_id), ctypes.sizeof(file_id)
    ):
        raise native_error()
    return f"{file_id.volume}:{int.from_bytes(bytes(file_id.identifier), 'little')}"


@contextmanager
def open_file(path, *, delete=False, create=False, directory_handle=None, directory=False):
    import msvcrt

    kernel = api()
    access = 0x80000000 | (0x10000 if delete or create else 0) | (0x40000000 if create else 0)
    if directory_handle:

        class UnicodeString(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ushort),
                ("maximum", ctypes.c_ushort),
                ("buffer", wintypes.LPWSTR),
            ]

        class ObjectAttributes(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.ULONG),
                ("root", wintypes.HANDLE),
                ("name", ctypes.POINTER(UnicodeString)),
                ("attributes", wintypes.ULONG),
                ("security", wintypes.LPVOID),
                ("qos", wintypes.LPVOID),
            ]

        class Status(ctypes.Structure):
            _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

        buffer = ctypes.create_unicode_buffer(path.name)
        name = UnicodeString(
            len(path.name.encode("utf-16-le")),
            ctypes.sizeof(buffer),
            ctypes.cast(buffer, wintypes.LPWSTR),
        )
        attributes = ObjectAttributes(
            ctypes.sizeof(ObjectAttributes),
            directory_handle,
            ctypes.pointer(name),
            0x1040,
            None,
            None,
        )
        nt = ctypes.WinDLL("ntdll")
        nt.NtCreateFile.argtypes = [
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.ULONG,
            ctypes.POINTER(ObjectAttributes),
            ctypes.POINTER(Status),
            wintypes.LPVOID,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.ULONG,
            wintypes.LPVOID,
            wintypes.ULONG,
        ]
        nt.NtCreateFile.restype = ctypes.c_long
        nt.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
        nt.RtlNtStatusToDosError.restype = wintypes.DWORD
        output, status = wintypes.HANDLE(), Status()
        # Relative leaf + OBJ_DONT_REPARSE; no path traversal during native create.
        result = nt.NtCreateFile(
            ctypes.byref(output),
            access | 0x00100000,
            ctypes.byref(attributes),
            ctypes.byref(status),
            None,
            0x10 if directory else 0x80,
            1,
            2 if create else 1,
            0x00200021 if directory else 0x00200060,
            None,
            0,
        )
        if result < 0:
            ctypes.set_last_error(nt.RtlNtStatusToDosError(result))
            raise native_error()
        handle = output.value
    else:
        handle = kernel.CreateFileW(
            str(path),
            access,
            1,
            None,
            1 if create else 3,
            0x02200000 if directory else 0x00200000,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            raise native_error()
    if directory:
        try:
            yield handle
        finally:
            kernel.CloseHandle(handle)
        return
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_RDWR if create else os.O_RDONLY))
    except Exception:
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(fd, "w+b" if create else "rb") as stream:
        yield stream


def rename_open_file(stream, target, *, directory_handle=None):
    import msvcrt

    encoded = (target.name if directory_handle else str(target)).encode("utf-16-le")

    class Rename(ctypes.Structure):
        _fields_ = [
            ("replace", ctypes.c_ubyte),
            ("root", wintypes.HANDLE),
            ("length", wintypes.DWORD),
            ("name", ctypes.c_wchar * (len(encoded) // 2 + 1)),
        ]

    info = Rename()
    info.root = directory_handle
    info.length = len(encoded)
    ctypes.memmove(ctypes.addressof(info) + Rename.name.offset, encoded, len(encoded))
    if directory_handle:

        class Status(ctypes.Structure):
            _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

        nt = ctypes.WinDLL("ntdll")
        nt.NtSetInformationFile.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Status),
            wintypes.LPVOID,
            wintypes.ULONG,
            ctypes.c_int,
        ]
        nt.NtSetInformationFile.restype = ctypes.c_long
        nt.RtlNtStatusToDosError.argtypes = [ctypes.c_long]
        nt.RtlNtStatusToDosError.restype = wintypes.DWORD
        status = Status()
        result = nt.NtSetInformationFile(
            msvcrt.get_osfhandle(stream.fileno()),
            ctypes.byref(status),
            ctypes.byref(info),
            ctypes.sizeof(info),
            10,
        )
        if result < 0:
            ctypes.set_last_error(nt.RtlNtStatusToDosError(result))
            raise native_error()
    elif not api().SetFileInformationByHandle(
        msvcrt.get_osfhandle(stream.fileno()), 3, ctypes.byref(info), ctypes.sizeof(info)
    ):
        raise native_error()


def delete_open_file(stream):
    import msvcrt

    info = ctypes.c_ubyte(1)
    if not api().SetFileInformationByHandle(
        msvcrt.get_osfhandle(stream.fileno()), 4, ctypes.byref(info), ctypes.sizeof(info)
    ):
        raise native_error()


def remove_empty_directory(path):
    kernel = api()
    handle = kernel.CreateFileW(str(path), 0x80010000, 1, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise native_error()
    try:
        with os.scandir(path) as entries:
            if next(entries, None) is not None:
                raise WorkspaceError("目录已有其他内容，不能撤销创建。")
        info = ctypes.c_ubyte(1)
        if not kernel.SetFileInformationByHandle(
            handle, 4, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise native_error()
    finally:
        kernel.CloseHandle(handle)
