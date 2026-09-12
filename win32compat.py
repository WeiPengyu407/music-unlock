#!/usr/bin/env python3
"""Windows 自己养的兼容包袱。别的平台这些函数是原样返回或走 shutil。"""
import os
import re
import shutil
import sys
from urllib.parse import unquote

# OneDrive「仅联机」打开失败时常见的 winerror
_CLOUD = {362, 395, 4390, 4393}


def enable_dpi_awareness():
    """必须在创建任何窗口之前调用。不做的话 125%/150% 缩放下 Tk 发糊或控件错位。"""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def long_path(path):
    """CreateFileW 的长路径前缀（\\\\?\\），绕开 MAX_PATH=260。已经带前缀的不重复加。"""
    if sys.platform != "win32" or not path:
        return path
    path = os.path.abspath(path)
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def for_child(path):
    """给 um/qmc 的路径：够长才加长路径前缀，短路径保持原样以免老工具不认。"""
    if sys.platform != "win32" or not path:
        return path
    path = os.path.abspath(path)
    return long_path(path) if len(path) >= 240 else path


def docker_bind(host_path, container_path):
    """Docker Desktop 的 -v：反斜杠、中文用户名都能过，前提是正斜杠。"""
    host_path = os.path.abspath(host_path)
    if sys.platform == "win32":
        host_path = host_path.replace("\\", "/")
    return f"{host_path}:{container_path}"


def parse_drop_paths(items):
    """资源管理器拖放：花括号、file:///C:/、Tcl 正斜杠。"""
    if isinstance(items, str):
        items = [items]
    out = []
    for raw in items:
        p = raw.strip().strip("{}")
        if p.startswith("file://"):
            p = unquote(p[7:])
            if re.match(r"^/[A-Za-z]:", p):
                p = p[1:]
        p = os.path.normpath(p)
        if p:
            out.append(p)
    return out


def hydrate(path):
    """戳一下 OneDrive 占位文件。还在云端则返回给用户看的原因，否则 None。"""
    try:
        with open(path, "rb") as f:
            f.read(1)
    except OSError as e:
        if cloud_blocked(e):
            return "文件还在网盘里，请先在资源管理器里打开一次再拖进来"
    return None


def writable_dir(preferred, fallback):
    """Program Files / 受控文件夹访问 会让「文件旁边新建目录」失败，改写到 fallback。"""
    for candidate in (preferred, fallback):
        try:
            os.makedirs(candidate, exist_ok=True)
            probe = os.path.join(candidate, ".mu_write")
            with open(probe, "wb") as f:
                f.write(b"x")
            os.remove(probe)
            return candidate
        except OSError:
            continue
    return preferred


def cloud_blocked(exc):
    return sys.platform == "win32" and getattr(exc, "winerror", None) in _CLOUD


def copy_even_if_locked(src, dst):
    """酷狗/浏览器常以共享锁占着 db。普通 copy 失败就用 FILE_SHARE_* 读。"""
    parent = os.path.dirname(os.path.abspath(dst))
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        shutil.copy2(src, dst)
        return
    except OSError:
        if sys.platform != "win32":
            raise
    _copy_shared(src, dst)


def _copy_shared(src, dst):
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    k.ReadFile.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    GENERIC_READ, FILE_SHARE, OPEN_EXISTING = 0x80000000, 7, 3
    invalid = ctypes.c_void_p(-1).value
    handle = k.CreateFileW(src, GENERIC_READ, FILE_SHARE, None, OPEN_EXISTING, 0x80, None)
    if handle in (None, invalid):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buf = ctypes.create_string_buffer(1024 * 1024)
        n = wintypes.DWORD()
        with open(dst, "wb") as out:
            while True:
                if not k.ReadFile(handle, buf, len(buf), ctypes.byref(n), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if n.value == 0:
                    break
                out.write(buf.raw[:n.value])
    finally:
        k.CloseHandle(handle)


def snapshot_sqlite(src, dest_dir):
    """连 -wal/-shm 一起拷走，给 um/sqlite 一个不被客户端锁住的副本。"""
    os.makedirs(dest_dir, exist_ok=True)
    dst = os.path.join(dest_dir, os.path.basename(src))
    copy_even_if_locked(src, dst)
    for suf in ("-wal", "-shm"):
        extra = src + suf
        if os.path.exists(extra):
            copy_even_if_locked(extra, dst + suf)
    return dst
