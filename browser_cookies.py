#!/usr/bin/env python3
"""跨浏览器读取 y.qq.com cookie（Firefox 明文 + Chromium 系加密解密）。

支持: Firefox / Chrome / Edge / Chromium / 360安全浏览器 / 360极速浏览器
系统: Linux / Windows / macOS

Chromium 系 cookie 加密原理:
- 主密钥存在 <profile>/Local State 的 os_crypt.encrypted_key (base64)
  - Windows: DPAPI 解密得主密钥 (AES-256)
  - macOS: keychain 里 "Chrome Safe Storage" 密码经 PBKDF2(saltysalt, pw, 1003) 派生
  - Linux: 优先读取 Secret Service 中的浏览器 Safe Storage 密码，兼容 peanuts 旧值
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


def _safe_storage_names(browser_name):
    names = {
        "chrome": ("Chrome Safe Storage", "chrome"),
        "edge": ("Microsoft Edge Safe Storage", "microsoft-edge"),
        "chromium": ("Chromium Safe Storage", "chromium"),
        "360": ("Chrome Safe Storage", "chrome"),
        "360安全": ("Chrome Safe Storage", "chrome"),
        "360极速": ("Chrome Safe Storage", "chrome"),
    }
    return names.get(browser_name, ("Chrome Safe Storage", browser_name))


def _derive_key(password, iterations):
    from hashlib import pbkdf2_hmac
    return pbkdf2_hmac("sha1", password, b"saltysalt", iterations, 16)


def _master_keys(browser_name, browser_root):
    """返回该浏览器可能使用的 AES 密钥，Linux 包含 keyring 与旧版回退。"""
    if OSKEY == "win32":
        ls_path = os.path.join(browser_root, "Local State")
        with open(ls_path, encoding="utf-8") as f:
            state = json.load(f)
        encrypted = base64.b64decode(state["os_crypt"]["encrypted_key"])
        if not encrypted.startswith(b"DPAPI"):
            raise RuntimeError("Local State 中没有 DPAPI 主密钥")
        return [_dpapi_decrypt(encrypted[5:])]
    if OSKEY == "darwin":
        import subprocess
        service, _application = _safe_storage_names(browser_name)
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"keychain 里没有 {service}")
        return [_derive_key(result.stdout.strip().encode(), 1003)]

    passwords = []
    _service, application = _safe_storage_names(browser_name)
    if shutil.which("secret-tool"):
        import subprocess
        for app in dict.fromkeys((application, browser_name, "chrome", "chromium")):
            result = subprocess.run(
                ["secret-tool", "lookup", "application", app],
                capture_output=True, timeout=10)
            password = result.stdout.strip()
            if result.returncode == 0 and password:
                passwords.append(password)
    passwords.append(b"peanuts")
    return list(dict.fromkeys(_derive_key(password, 1) for password in passwords))


def _decrypt_value(enc, keys, host):
    """解密单个 encrypted_value。"""
    AES = _aes()
    for key in keys:
        try:
            if enc[:3] in (b"v10", b"v11"):
                payload = enc[3:]
                if not payload or len(payload) % 16:
                    continue
                pt = AES.new(key, AES.MODE_CBC, b" " * 16).decrypt(payload)
                pad = pt[-1]
                if not 0 < pad <= 16 or pt[-pad:] != bytes([pad]) * pad:
                    continue
                pt = pt[:-pad]
            elif enc[:3] == b"v20":
                payload = enc[3:]
                if len(payload) < 28:
                    continue
                nonce, ciphertext, tag = payload[:12], payload[12:-16], payload[-16:]
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                pt = cipher.decrypt_and_verify(ciphertext, tag)
            else:
                return None

            from hashlib import sha256
            host_digest = sha256(host.encode()).digest()
            if pt.startswith(host_digest):
                pt = pt[len(host_digest):]
            return pt
        except (ValueError, KeyError):
            continue
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
        keys = _master_keys(browser_name, root)
    except Exception:
        return {}
    out = {}
    for db in dbs:
        with tempfile.TemporaryDirectory(prefix=f"mu_ck_{browser_name}_") as tmpdir:
            tmp = os.path.join(tmpdir, "Cookies")
            try:
                shutil.copy2(db, tmp)
                for suffix in ("-wal", "-shm"):
                    if os.path.exists(db + suffix):
                        shutil.copy2(db + suffix, tmp + suffix)
                with sqlite3.connect(tmp) as con:
                    rows = con.execute(
                        "select host_key, name, value, encrypted_value "
                        "from cookies where host_key like ?",
                        (HOSTS_LIKE,)).fetchall()
                for host, name, value, enc in rows:
                    if name not in WANT_KEYS or name in out:
                        continue
                    try:
                        plain = value.encode() if value else _decrypt_value(enc, keys, host)
                        if plain:
                            out[name] = plain.decode("utf-8")
                    except (UnicodeDecodeError, ValueError):
                        pass
            except (OSError, sqlite3.Error):
                pass
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
