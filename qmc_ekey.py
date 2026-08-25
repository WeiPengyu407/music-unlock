#!/usr/bin/env python3
"""QMC musicex (mflac/mgg, QQ音乐>=19.57) ekey 获取模块。

原理：musicex 文件的音频由 ekey 加密，ekey 只能从 QQ 音乐 GetEVkey 接口下发。
本模块只需一次性提供任意 QQ 账号凭据（uin + authst，存配置即可），之后永久离线解密。
凭据来源优先级：配置文件 > Firefox y.qq.com 登录态导入。
"""
import json
import os
import struct
import urllib.error
import urllib.request

API = "https://u.y.qq.com/cgi-bin/musicu.fcg"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
CONF = os.path.expanduser("~/.config/music-unlock/qqmusic.json")


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
        with urllib.request.urlopen(req, timeout=15) as r:
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


def load_credentials():
    """凭据来源（按序）：
    1. 配置文件 ~/.config/music-unlock/qqmusic.json: {"uin": "...", "authst": "..."}
    2. QQ 音乐客户端数据目录（配置 {"qqmusic_dir": "..."} 指定）
    3. Firefox 里 y.qq.com 的网页登录态（import_from_browser）
    """
    try:
        d = json.load(open(CONF))
        if d.get("uin") and d.get("authst"):
            return d["uin"], d["authst"]
        if d.get("qqmusic_dir"):
            u, a = import_from_qq_dir(d["qqmusic_dir"])
            if u and a:
                return u, a
    except Exception:
        pass
    return import_from_browser()


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


def _firefox_cookie_db():
    """定位 Firefox cookies.sqlite（.default-release / .default 配置目录）。"""
    import glob
    base = os.path.expanduser("~/.config/mozilla/firefox")
    for pat in ("*.default-release", "*.default*", "*.default"):
        for p in glob.glob(os.path.join(base, pat, "cookies.sqlite")):
            return p
    return None


def _read_browser_cookies(hosts=("y.qq.com", ".qq.com")):
    """从 Firefox cookies.sqlite 读出指定域名的 cookie 字典。"""
    import shutil
    import sqlite3
    import tempfile
    db = _firefox_cookie_db()
    if not db:
        return {}
    tmp = os.path.join(tempfile.gettempdir(), "mu_ck.sqlite")
    shutil.copy(db, tmp)
    wal = db + "-wal"
    if os.path.exists(wal):
        shutil.copy(wal, tmp + "-wal")
    out = {}
    try:
        con = sqlite3.connect(tmp)
        for host, name, value in con.execute(
                "select host, name, value from moz_cookies where host like '%qq.com%'"):
            if any(h in host for h in hosts):
                out[name] = value
        con.close()
    finally:
        for f in (tmp, tmp + "-wal"):
            os.path.exists(f) and os.remove(f)
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
