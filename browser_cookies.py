#!/usr/bin/env python3
"""跨浏览器读取 y.qq.com cookie（Firefox 明文 + Chromium 系加密解密）。

支持: Firefox / Chrome / Edge / Chromium / 360安全浏览器 / 360极速浏览器
系统: Linux / Windows / macOS

Chromium 系 cookie 加密原理:
- 主密钥存在 <profile>/Local State 的 os_crypt.encrypted_key (base64)
  - Windows: DPAPI 解密得主密钥 (AES-256)
  - macOS: keychain 里 "Chrome Safe Storage" 密码经 PBKDF2(saltysalt, pw, 1003) 派生
  - Linux: v10 固定 PBKDF2('saltysalt', 'peanuts', 1, 16)
- cookie 值: 'v10'/'v11' 前缀 = AES-CBC(IV=16空格); 'v20' 前缀 = AES-GCM(nonce=值[3:15])
"""
import base64
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile

HOSTS_LIKE = "%qq.com%"
WANT_KEYS = ("uin", "euin", "qqmusic_key", "qqmusic_fromtag")

BROWSERS = {
    "win32": {
        "chrome": "~/AppData/Local/Google/Chrome/User Data",
        "edge": "~/AppData/Local/Microsoft/Edge/User Data",
        "chromium": "~/AppData/Local/Chromium/User Data",
        "360安全": "~/AppData/Roaming/360se6/User Data",
        "360极速": "~/AppData/Roaming/360Chrome/Chrome/User Data",
    },
    "linux": {
        "chrome": "~/.config/google-chrome",
        "edge": "~/.config/microsoft-edge",
        "chromium": "~/.config/chromium",
        "360": "~/.config/360chrome",
    },
    "darwin": {
        "chrome": "~/Library/Application Support/Google/Chrome",
        "edge": "~/Library/Application Support/Microsoft Edge",
        "chromium": "~/Library/Application Support/Chromium",
    },
}
OSKEY = "win32" if sys.platform == "win32" else ("darwin" if sys.platform == "darwin" else "linux")


def _aes():
    """惰性加载 pycryptodome（mu-venv 兜底）。"""
    try:
        from Crypto.Cipher import AES
        return AES
    except ImportError:
        venv = os.path.expanduser("~/.local/share/mu-venv/lib")
        for p in glob.glob(venv + "/python*/site-packages"):
            if p not in sys.path:
                sys.path.insert(0, p)
        from Crypto.Cipher import AES
        return AES


def _dpapi_decrypt(data):
    """Windows DPAPI 解密（仅 win32）。"""
    import ctypes
    import ctypes.wintypes as wt

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    blob_in = BLOB(len(data), ctypes.cast(data, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise RuntimeError("CryptUnprotectData failed")
    out = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return out


def _master_key(browser_root):
    """从 Local State 提取解密的 AES 主密钥。"""
    ls_path = os.path.join(browser_root, "Local State")
    st = json.load(open(ls_path, encoding="utf-8"))
    enc_key = base64.b64decode(st["os_crypt"]["encrypted_key"])
    assert enc_key[:5] == b"DPAPI"
    enc_key = enc_key[5:]
    if OSKEY == "win32":
        return _dpapi_decrypt(enc_key)
    if OSKEY == "darwin":
        import subprocess
        pw = subprocess.run(
            ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
            capture_output=True, text=True)
        if pw.returncode != 0:
            raise RuntimeError("keychain 里没有 Chrome Safe Storage")
        from hashlib import pbkdf2_hmac
        return pbkdf2_hmac("sha1", pw.stdout.strip().encode(), b"saltysalt", 1003, 16)
    # linux: v10 固定派生（无 keyring 或 keyring 默认密码时 Chrome 用它）
    from hashlib import pbkdf2_hmac
    return pbkdf2_hmac("sha1", b"peanuts", b"saltysalt", 1, 16)


def _decrypt_value(enc, key):
    """解密单个 encrypted_value。"""
    AES = _aes()
    if enc[:3] in (b"v10", b"v11"):
        iv = b" " * 16
        pt = AES.new(key, AES.MODE_CBC, iv).decrypt(enc[3:])
        pad = pt[-1]
        return pt[:-pad] if 0 < pad <= 16 else pt
    if enc[:3] == b"v20":
        return AES.new(key, AES.MODE_GCM, nonce=enc[3:15]).decrypt(enc[15:])
    return None


def _cookie_dbs(root):
    """浏览器 profile 下的所有 Cookies 数据库路径。"""
    pats = ["Default/Cookies", "Default/Network/Cookies",
            "Profile */Cookies", "Profile */Network/Cookies",
            "Cookies", "Network/Cookies"]
    out = []
    for p in pats:
        out += glob.glob(os.path.join(root, p))
    return [p for p in out if os.path.exists(p)]


def _read_chromium_cookies(browser_name, root):
    """读一个 Chromium 系浏览器的 y.qq.com cookie。"""
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return {}
    dbs = _cookie_dbs(root)
    if not dbs:
        return {}
    try:
        key = _master_key(root)
    except Exception:
        return {}
    out = {}
    for db in dbs:
        tmp = os.path.join(tempfile.gettempdir(), f"mu_ck_{browser_name}.sqlite")
        try:
            shutil.copy(db, tmp)
            con = sqlite3.connect(tmp)
            rows = con.execute(
                "select host_key, name, encrypted_value from cookies where host_key like ?",
                (HOSTS_LIKE,)).fetchall()
            con.close()
            for _host, name, enc in rows:
                if name not in WANT_KEYS or name in out:
                    continue
                try:
                    v = _decrypt_value(enc, key)
                    if v:
                        out[name] = v.decode("utf-8", "ignore")
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            os.path.exists(tmp) and os.remove(tmp)
    return out


def read_all_browser_cookies():
    """遍历所有支持的浏览器，返回 {browser: {cookie名: 值}}（非空的才返回）。"""
    result = {}
    # Firefox（明文）
    try:
        from qmc_ekey import _read_browser_cookies as ff
        c = ff()
        if c:
            result["firefox"] = c
    except Exception:
        pass
    for name, root in BROWSERS[OSKEY].items():
        c = _read_chromium_cookies(name, root)
        if c:
            result[name] = c
    return result


def find_qq_credentials():
    """从所有浏览器里找 (uin, qqmusic_key)，返回 (uin, key, 来源浏览器) 或 (None, None, None)。"""
    for browser, ck in read_all_browser_cookies().items():
        uin = ck.get("uin") or ck.get("euin")
        key = ck.get("qqmusic_key")
        if uin and key:
            return uin.lstrip("o"), key, browser
    return None, None, None
