#!/usr/bin/env python3
"""QMC musicex (mflac/mgg, QQ音乐>=19.57) ekey 获取模块。

原理：musicex 文件的音频由 ekey 加密，ekey 只能从 QQ 音乐 GetEVkey 接口下发。
本模块只需一次性提供任意 QQ 账号凭据（uin + authst，存配置即可），之后永久离线解密。
凭据来源优先级：配置文件 > Firefox y.qq.com 登录态导入。
"""
import json
import os
import struct
import sys
import urllib.error
import urllib.request

API = "https://u.y.qq.com/cgi-bin/musicu.fcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def default_conf_path():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        return os.path.join(base, "music-unlock", "qqmusic.json")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/music-unlock/qqmusic.json")
    return os.path.expanduser("~/.config/music-unlock/qqmusic.json")


CONF = default_conf_path()


class EkeyFetchError(Exception):
    """QQ 密钥接口调用失败。"""


def parse_musicex_footer(path):
    """从 musicex 文件尾部分析出 (song_id, media_mid, filename)。不是 musicex 返回 None。"""
    with open(path, "rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        if file_size < 16:
            return None
        f.seek(-16, 2)
        tail = f.read()
    if tail[-8:] != b"musicex\x00":
        return None
    footer_size, version = struct.unpack("<II", tail[0:8])
    if version != 1 or not 16 < footer_size <= min(file_size, 16 * 1024 * 1024):
        return None
    with open(path, "rb") as f:
        f.seek(-footer_size, 2)
        meta = f.read(footer_size - 16)
    if len(meta) < 0x48:
        return None
    song_id = struct.unpack("<I", meta[0:4])[0]

    def u16s(off, maxlen):
        return meta[off:off + maxlen].decode("utf-16-le", "ignore").split("\x00")[0]

    return song_id, u16s(0x0C, 60), u16s(0x48, 68)


def fetch_ekey(media_mid, filename, uin=None, authst=None, cookies=None):
    """调 GetEVkey 接口取 ekey。失败时抛出带原因的 EkeyFetchError。"""
    if cookies is None and not (uin and authst):
        uin, authst = load_credentials()
    if cookies is None and not (uin and authst):
        raise EkeyFetchError("无 QQ 登录态（点「导入QQ登录态」）")
    body = json.dumps({
        "comm": {"authst": authst or "", "ct": "19", "cv": "1859", "uin": uin or "0", "tmeLoginType": "3"},
        "req_1": {"module": "music.vkey.GetEVkey", "method": "CgiGetEVkey",
                  "param": {"filename": [filename], "guid": "10000", "songmid": [media_mid],
                            "songtype": [1], "uin": uin or "0", "loginflag": 1, "platform": "27", "ctx": 1}},
    }).encode()
    headers = {"Content-Type": "application/json", "User-Agent": UA, "Referer": "https://y.qq.com/"}
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req = urllib.request.Request(API, data=body, headers=headers)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=15) as r:
            d = json.loads(r.read())
        info = d["req_1"]["data"]["midurlinfo"][0]
        ekey = info.get("ekey") or ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise EkeyFetchError(f"QQ 密钥请求失败：{reason}") from exc
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise EkeyFetchError("QQ 密钥接口返回异常，登录态可能已失效") from exc
    if not ekey:
        raise EkeyFetchError("QQ 密钥为空，登录态可能已失效")
    return ekey


def saved_credentials():
    """只读已落盘凭据，不扫浏览器（给 GUI 主线程用）。"""
    try:
        with open(CONF, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("uin") and d.get("authst"):
            return d["uin"], d["authst"]
        if d.get("qqmusic_dir"):
            u, a = import_from_qq_dir(d["qqmusic_dir"])
            if u and a:
                return u, a
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return None, None


def load_credentials():
    """凭据来源（按序）：已保存配置 → QQ 音乐客户端 → 浏览器。"""
    uin, authst = saved_credentials()
    if uin and authst:
        return uin, authst
    uin, authst, _src = import_credentials()
    return uin, authst


def qqmusic_dirs():
    """Windows QQ 音乐 PC 客户端数据目录。亲戚用的是这个，不是 Firefox。"""
    if sys.platform != "win32":
        return []
    roaming = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    return [
        os.path.join(roaming, "Tencent", "QQMusic"),
        os.path.join(local, "Tencent", "QQMusic"),
        os.path.join(roaming, "QQMusic"),
        os.path.join(local, "QQMusic"),
    ]


def import_from_qq_client():
    """从本机 QQ 音乐客户端导入 uin + authst，成功则落盘。"""
    import glob
    for d in qqmusic_dirs():
        for pat in ("QQMusicServiceConfig.ini", os.path.join("*", "QQMusicServiceConfig.ini")):
            for cfg in glob.glob(os.path.join(d, pat)):
                uin, authst = import_from_qq_dir(os.path.dirname(cfg))
                if uin and authst:
                    save_credentials(uin, authst)
                    return uin, authst
    return None, None


def import_credentials():
    """自动导入：QQ 音乐客户端 → 浏览器。返回 (uin, authst, 来源)。"""
    uin, authst = import_from_qq_client()
    if uin:
        return uin, authst, "QQ音乐客户端"
    uin, authst = import_from_browser()
    if uin:
        return uin, authst, "浏览器"
    return None, None, None


def import_from_qq_dir(qqdir):
    """从 QQ 音乐客户端数据目录读取 uin + authst（与 qmc-decoder 的文件策略一致）。"""
    import re
    uin = None
    cfg = os.path.join(qqdir, "QQMusicServiceConfig.ini")
    if os.path.exists(cfg):
        for line in open(cfg, encoding="utf-8", errors="ignore"):
            m = re.match(r"(?i)uin\s*=\s*(.+)", line.strip())
            if m and m.group(1).strip() not in ("", "0"):
                uin = m.group(1).strip()
                break
    authst = None
    for name in ("SetCookie.dat", "_SetCookie.dat"):
        p = os.path.join(qqdir, name)
        if not os.path.exists(p):
            continue
        data = open(p, "rb").read()
        m = re.search(rb'"authst"\s*:\s*"([A-Za-z0-9+/=_-]{10,})"', data)
        if m:
            authst = m.group(1).decode()
            break
        # 兜底：最长的带填充 base64 串
        for m in sorted(re.findall(rb'[A-Za-z0-9+/]{30,}={1,2}', data), key=len, reverse=True):
            authst = m.decode()
            break
        if authst:
            break
    return (uin, authst) if uin and authst else (None, None)


def save_credentials(uin, authst):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    fd = os.open(CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"uin": uin, "authst": authst}, f, indent=1)


def _firefox_profile_roots():
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA") or os.path.join(home, r"AppData\Roaming")
        return [os.path.join(roaming, "Mozilla", "Firefox", "Profiles")]
    if sys.platform == "darwin":
        return [os.path.join(home, "Library", "Application Support", "Firefox", "Profiles")]
    return [
        os.path.join(home, ".mozilla", "firefox"),
        os.path.join(home, ".config", "mozilla", "firefox"),
        os.path.join(home, "snap", "firefox", "common", ".mozilla", "firefox"),
        os.path.join(home, ".var", "app", "org.mozilla.firefox", ".mozilla", "firefox"),
    ]


def _firefox_cookie_dbs():
    import glob
    found, seen = [], set()
    for base in _firefox_profile_roots():
        for pat in ("*.default-release", "*.default*", "Profiles/*.default-release", "Profiles/*.default*"):
            for p in glob.glob(os.path.join(base, pat, "cookies.sqlite")):
                if p not in seen:
                    seen.add(p)
                    found.append(p)
    return found


def _read_browser_cookies(hosts=("y.qq.com", ".qq.com")):
    """从 Firefox cookies.sqlite 读出指定域名的 cookie 字典。"""
    import sqlite3
    import tempfile
    out = {}
    for db in _firefox_cookie_dbs():
        with tempfile.TemporaryDirectory(prefix="mu_ff_") as tmpdir:
            tmp = os.path.join(tmpdir, "cookies.sqlite")
            try:
                import win32compat
                win32compat.copy_even_if_locked(db, tmp)
                wal = db + "-wal"
                if os.path.exists(wal):
                    win32compat.copy_even_if_locked(wal, tmp + "-wal")
                con = sqlite3.connect(tmp)
                for host, name, value in con.execute(
                        "select host, name, value from moz_cookies where host like '%qq.com%'"):
                    if name not in out and any(h in host for h in hosts):
                        out[name] = value
                con.close()
            except (OSError, sqlite3.Error):
                continue
        if out:
            break
    return out


def import_from_browser():
    """从浏览器（Firefox/Chrome/Edge/Chromium/360）导入 y.qq.com 登录态。

    提取 uin 和 qqmusic_key（网页登录令牌，等价于客户端 authst），成功则写入配置文件永久复用。
    未验证前说明：qqmusic_key 调 GetEVkey 是否被接受取决于腾讯服务端，失败时返回 (None, None)。
    """
    import browser_cookies
    uin, key, _src = browser_cookies.find_qq_credentials()
    if uin and key:
        save_credentials(uin, key)
        return uin, key
    return None, None
