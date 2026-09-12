#!/usr/bin/env python3
"""酷狗新版 .kgg 解密的密钥库（KGMusicV3.db）定位。
新版 kgg 的密钥不在文件里，存在酷狗 PC 客户端（win32 v11）的私有数据库
KGMusicV3.db 中（与 QQ musicex 把 ekey 锁进 mmkv 同一套路）。
本模块负责在常见位置自动找库，并记住找到（或用户最后兜底选定）的路径。"""
import os
import sys

if os.name == "nt":
    MU_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local")),
        "music-unlock")
else:
    MU_DIR = os.path.expanduser("~/.local/share/music-unlock")
CONF = os.path.join(MU_DIR, "kgg_db_path.txt")
DB_NAME = "KGMusicV3.db"

def default_roots():
    """Windows 只找酷狗自己的目录；不要扫整个 AppData（微信/浏览器会把扫描拖死）。"""
    if os.name == "nt":
        roaming = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        local = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return [
            os.path.join(roaming, "KuGou8"),
            os.path.join(roaming, "Kugou8"),
            os.path.join(roaming, "KuGou"),
            os.path.join(local, "KuGou8"),
            os.path.join(local, "KuGou"),
        ]
    return [
        "~/.cxoffice",
        "~/.wine",
        "~/.local/share/wineprefixes",
        "~/Games",
        "~/Applications",
    ]


ROOTS = default_roots()

SKIP_DIRS = {
    "windows", "system32", "syswow64", "winsxs", "node_modules",
    ".git", "$recycle.bin", "temp", "tmp",
    "steam", "steamapps", ".steam",
}


def _remember(path):
    os.makedirs(MU_DIR, exist_ok=True)
    with open(CONF, "w", encoding="utf-8") as f:
        f.write(path)
    return path


def saved_db():
    try:
        with open(CONF, encoding="utf-8") as f:
            p = f.read().strip()
        return p if p and os.path.exists(p) else None
    except OSError:
        return None


def set_db(path):
    return _remember(path)


def usable_db(path):
    """Windows 上酷狗开着会锁 KGMusicV3.db，拷一份给 um 用。"""
    import win32compat
    if sys.platform != "win32":
        return path
    return win32compat.snapshot_sqlite(path, os.path.join(MU_DIR, "kgg-snap"))


def find_db():
    """自动搜 KGMusicV3.db：先 remembered，再扫常见根目录（限深防慢）。"""
    p = saved_db()
    if p:
        return p
    for root in ROOTS:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS]
            if depth > 6:
                dirnames[:] = []
                continue
            if DB_NAME in filenames:
                return _remember(os.path.join(dirpath, DB_NAME))
    return None
