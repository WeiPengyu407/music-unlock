import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import apple_music
import browser_cookies
import kgg
import mg3d
import music_unlock
import qmc_ekey
import win32compat


class FileDetectionTests(unittest.TestCase):
    def test_only_known_encrypted_extensions_are_accepted(self):
        self.assertTrue(music_unlock.is_music_file("song.ncm"))
        self.assertTrue(music_unlock.is_music_file("song.mflac0"))
        self.assertTrue(music_unlock.is_music_file("song.mg3d"))
        self.assertTrue(music_unlock.is_music_file("song.kgg"))
        self.assertFalse(music_unlock.is_music_file("README"))
        self.assertFalse(music_unlock.is_music_file("song.mp3"))

    def test_collect_preserves_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp, "album")
            nested.mkdir()
            Path(nested, "song.ncm").touch()
            Path(nested, "cover.jpg").touch()

            self.assertEqual(
                music_unlock.collect([tmp]),
                [(str(Path(nested, "song.ncm")), os.path.join("album", "song.ncm"))],
            )

    def test_retry_skips_successful_items(self):
        app = SimpleNamespace(
            items=[
                ["done.ncm", "done.ncm", " ✓"],
                ["retry.ncm", "retry.ncm", " ✗ old error"],
            ],
            outdir=None,
            set_status=mock.Mock(),
            unlock=mock.Mock(return_value=(True, "")),
            set_row=mock.Mock(),
            run_btn=SimpleNamespace(after=lambda _delay, callback: callback()),
            open_btn=SimpleNamespace(after=lambda _delay, callback: callback()),
        )
        app.run_btn.config = mock.Mock()
        app.open_btn.config = mock.Mock()

        music_unlock.App.work(app)

        app.unlock.assert_called_once_with("retry.ncm")
        app.set_row.assert_called_once_with(1, " ✓")

    def test_unlock_crash_still_reenables_run_button(self):
        app = SimpleNamespace(
            items=[["boom.ncm", "boom.ncm", ""]],
            outdir="/tmp",
            set_status=mock.Mock(),
            unlock=mock.Mock(side_effect=RuntimeError("boom")),
            set_row=mock.Mock(),
            run_btn=SimpleNamespace(after=lambda _delay, callback: callback()),
            open_btn=SimpleNamespace(after=lambda _delay, callback: callback()),
        )
        app.run_btn.config = mock.Mock()
        app.open_btn.config = mock.Mock()
        music_unlock.App.work(app)
        app.set_row.assert_called_once_with(0, " ✗ boom")
        app.run_btn.config.assert_called_with(state="normal")

    def test_kgg_goes_straight_to_kgg_unlock(self):
        app = SimpleNamespace(outdir=None, unlock_kgg=mock.Mock(return_value=(True, "")))
        with mock.patch.object(music_unlock.subprocess, "run") as run:
            ok, _why = music_unlock.App.unlock(app, "/tmp/song.kgg")
        self.assertTrue(ok)
        run.assert_not_called()
        app.unlock_kgg.assert_called_once_with("/tmp/song.kgg")


class QmcEkeyTests(unittest.TestCase):
    def test_short_file_is_not_musicex(self):
        with tempfile.NamedTemporaryFile() as file:
            file.write(b"short")
            file.flush()
            self.assertIsNone(qmc_ekey.parse_musicex_footer(file.name))

    def test_musicex_footer_is_parsed(self):
        metadata = bytearray(0x90)
        metadata[0:4] = struct.pack("<I", 42)
        metadata[0x0C:0x0C + len("media-mid".encode("utf-16-le"))] = \
            "media-mid".encode("utf-16-le")
        metadata[0x48:0x48 + len("track.mflac".encode("utf-16-le"))] = \
            "track.mflac".encode("utf-16-le")
        footer_size = len(metadata) + 16
        with tempfile.NamedTemporaryFile() as file:
            file.write(metadata)
            file.write(struct.pack("<II", footer_size, 1))
            file.write(b"musicex\0")
            file.flush()
            self.assertEqual(
                qmc_ekey.parse_musicex_footer(file.name),
                (42, "media-mid", "track.mflac"),
            )

    def test_missing_credentials_has_specific_error(self):
        with mock.patch.object(qmc_ekey, "load_credentials", return_value=(None, None)):
            with self.assertRaisesRegex(qmc_ekey.EkeyFetchError, "无 QQ 登录态"):
                qmc_ekey.fetch_ekey("mid", "track.mflac")

    def test_saved_credentials_does_not_scan_browsers(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp, "qqmusic.json")
            conf.write_text('{"uin":"1","authst":"token"}', encoding="utf-8")
            with mock.patch.object(qmc_ekey, "CONF", str(conf)):
                with mock.patch.object(qmc_ekey, "import_from_browser") as scan:
                    self.assertEqual(qmc_ekey.saved_credentials(), ("1", "token"))
                    scan.assert_not_called()

    def test_windows_conf_uses_appdata(self):
        with mock.patch.object(qmc_ekey.sys, "platform", "win32"):
            with mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\x\AppData\Roaming"}):
                path = qmc_ekey.default_conf_path().replace("\\", "/")
        self.assertTrue(path.endswith("music-unlock/qqmusic.json"))
        self.assertIn("AppData/Roaming", path)

    def test_windows_qqmusic_client_dirs(self):
        with mock.patch.object(qmc_ekey.sys, "platform", "win32"):
            with mock.patch.dict(os.environ, {
                "APPDATA": r"C:\Users\x\AppData\Roaming",
                "LOCALAPPDATA": r"C:\Users\x\AppData\Local",
            }):
                dirs = [d.replace("\\", "/") for d in qmc_ekey.qqmusic_dirs()]
        self.assertTrue(any(d.endswith("Tencent/QQMusic") for d in dirs))

    def test_import_credentials_prefers_qq_client(self):
        with mock.patch.object(qmc_ekey, "import_from_qq_client", return_value=("10001", "token")):
            with mock.patch.object(qmc_ekey, "import_from_browser") as br:
                self.assertEqual(
                    qmc_ekey.import_credentials(),
                    ("10001", "token", "QQ音乐客户端"),
                )
                br.assert_not_called()

    def test_linux_firefox_roots_include_standard_mozilla(self):
        with mock.patch.object(qmc_ekey.sys, "platform", "linux"):
            roots = qmc_ekey._firefox_profile_roots()
        self.assertTrue(any(r.endswith(".mozilla/firefox") for r in roots))
        self.assertTrue(any(".config/mozilla/firefox" in r for r in roots))


class BrowserCookieTests(unittest.TestCase):
    def test_cbc_cookie_decryption_and_host_digest_removal(self):
        try:
            from Crypto.Cipher import AES
            from hashlib import sha256
        except ImportError:
            self.skipTest("pycryptodome is not installed")

        key = b"0123456789abcdef"
        host = ".qq.com"
        plain = sha256(host.encode()).digest() + b"cookie-value"
        pad = 16 - len(plain) % 16
        encrypted = b"v10" + AES.new(key, AES.MODE_CBC, b" " * 16).encrypt(
            plain + bytes([pad]) * pad)

        self.assertEqual(
            browser_cookies._decrypt_value(encrypted, [key], host),
            b"cookie-value",
        )

    def test_gcm_cookie_authentication_is_verified(self):
        try:
            from Crypto.Cipher import AES
        except ImportError:
            self.skipTest("pycryptodome is not installed")

        key = b"0" * 32
        nonce = b"1" * 12
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(b"cookie-value")
        encrypted = b"v20" + nonce + ciphertext + tag

        self.assertEqual(
            browser_cookies._decrypt_value(encrypted, [key], ".qq.com"),
            b"cookie-value",
        )
        tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
        self.assertIsNone(browser_cookies._decrypt_value(tampered, [key], ".qq.com"))


class AppleMusicTests(unittest.TestCase):
    def test_image_tag_matches_target_architecture(self):
        with mock.patch.object(apple_music, "_target_arch", return_value="arm64-v8a"):
            self.assertEqual(apple_music._image_tag(), "wrapper-v2:arm64")
        with mock.patch.object(apple_music, "_target_arch", return_value="x86_64"):
            self.assertEqual(apple_music._image_tag(), "wrapper-v2:latest")

    def test_chain_reports_missing_downloader(self):
        with mock.patch.multiple(
            apple_music,
            FROZEN=False,
            GAMDL="/path/that/does/not/exist",
            wrapper_up=mock.Mock(return_value=True),
            playback_ready=mock.Mock(return_value=True),
            is_logged_in=mock.Mock(return_value=True),
        ):
            self.assertEqual(
                apple_music.check_chain(),
                (False, "downloader", "安装不完整，缺少下载组件"),
            )

    def test_is_apple_url_accepts_share_hosts(self):
        self.assertTrue(apple_music.is_apple_url("https://music.apple.com/cn/album/x"))
        self.assertTrue(apple_music.is_apple_url("https://itunes.apple.com/album/id123"))
        self.assertTrue(apple_music.is_apple_url("https://geo.music.apple.com/cn/song/x"))
        self.assertTrue(apple_music.is_apple_url("https://www.itunes.apple.com/cn/album/x"))
        self.assertFalse(apple_music.is_apple_url("https://example.com/music.apple.com"))
        self.assertFalse(apple_music.is_apple_url("music.apple.com/cn/album/x"))

    def test_wrapper_does_not_steal_host_port_80(self):
        self.assertEqual(apple_music.WRAPPER_PORT, 18480)
        self.assertEqual(apple_music.GAMDL_VENV,
                         os.path.join(apple_music.MU_DIR, "gamdl-venv"))

    def test_wrapper_up_falls_back_to_legacy_port_80(self):
        apple_music._active_port = None

        def fake_req(method, path, payload=None, timeout=15, port=None):
            if port == 80:
                return {"status": "ok"}
            raise apple_music.WrapperError("nope")

        try:
            with mock.patch.object(apple_music, "_req", side_effect=fake_req):
                with mock.patch.object(apple_music, "_try_start_container"):
                    self.assertTrue(apple_music.wrapper_up())
            self.assertEqual(apple_music._active_port, 80)
        finally:
            apple_music._active_port = None

    def test_apk_urls_try_cn_mirrors_before_github(self):
        urls = apple_music._apk_urls()
        self.assertTrue(urls[-1].startswith("https://github.com/"))
        self.assertGreater(len(urls), 1)
        self.assertTrue(all(u.endswith("apple-music-3.6.0-beta.apkm") for u in urls))
        self.assertTrue(any("ghfast.top" in u for u in urls[:-1]))

    def test_fetch_apk_reuses_local_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp, "apple-music-3.6.0-beta.apkm")
            cache.write_bytes(b"0" * 50_000_000)
            with mock.patch.object(apple_music, "APK_CACHE", str(cache)):
                with mock.patch.object(subprocess, "run") as run:
                    self.assertEqual(apple_music.fetch_apk(), str(cache))
                    run.assert_not_called()

    def test_fetch_apk_goes_direct_without_curl_or_proxy(self):
        import io
        import urllib.request
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp, "apple-music-3.6.0-beta.apkm")
            opener = mock.Mock()

            class Resp:
                def __enter__(self):
                    return io.BytesIO(b"0" * 50_000_000)

                def __exit__(self, *args):
                    return False

            opener.open.return_value = Resp()
            with mock.patch.object(apple_music, "APK_CACHE", str(cache)):
                with mock.patch.object(apple_music, "MU_DIR", tmp):
                    with mock.patch.object(subprocess, "run") as run:
                        with mock.patch.object(apple_music.urllib.request, "build_opener",
                                               return_value=opener) as bo:
                            self.assertEqual(apple_music.fetch_apk(), str(cache))
            run.assert_not_called()
            handler = bo.call_args[0][0]
            self.assertIsInstance(handler, urllib.request.ProxyHandler)
            self.assertEqual(handler.proxies, {})
            self.assertTrue(cache.is_file())

    def test_download_timeout_kills_gamdl(self):
        proc = mock.Mock()
        proc.stdout = iter(())
        proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="gamdl", timeout=1), None]
        apple_music._active_port = None
        with mock.patch.object(apple_music, "FROZEN", False):
            with mock.patch.object(apple_music, "GAMDL", "/bin/true"):
                with mock.patch.object(subprocess, "Popen", return_value=proc) as popen:
                    with tempfile.TemporaryDirectory() as tmp:
                        ok, why = apple_music.download("https://music.apple.com/cn/song/x", tmp)
        self.assertFalse(ok)
        self.assertIn("超时", why)
        proc.kill.assert_called_once()
        self.assertIn("http://127.0.0.1:18480", popen.call_args[0][0])


def _tiny_wav():
    data = b"\x00\x00" * 80
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


class Mg3dTests(unittest.TestCase):
    def test_synthetic_wav_roundtrip(self):
        wav = _tiny_wav()
        key = b"0123456789ABCDEF0123456789ABCDEF"
        self.assertEqual(wav[0x40:0x60], b"\x00" * 32)
        enc = bytes((b + key[i % 32]) & 0xFF for i, b in enumerate(wav))
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "song.mg3d")
            src.write_bytes(enc)
            ok, out = mg3d.mg3d_decrypt(str(src), tmp)
            self.assertTrue(ok, out)
            self.assertEqual(Path(out).read_bytes(), wav)

    def test_garbage_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "nope.mg3d").write_bytes(b"not a mg3d file" * 20)
            ok, why = mg3d.mg3d_decrypt(str(Path(tmp, "nope.mg3d")), tmp)
            self.assertFalse(ok)
            self.assertIn("密钥", why)


class KggDbTests(unittest.TestCase):
    def test_first_scan_returns_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp, "KuGou8")
            nested.mkdir()
            db = nested / "KGMusicV3.db"
            db.write_bytes(b"x")
            confdir = Path(tmp, "conf")
            with mock.patch.multiple(
                kgg,
                ROOTS=[tmp],
                MU_DIR=str(confdir),
                CONF=str(confdir / "kgg_db_path.txt"),
            ):
                found = kgg.find_db()
            self.assertEqual(found, str(db))
            self.assertEqual((confdir / "kgg_db_path.txt").read_text(), str(db))

    def test_windows_kugou_looks_in_kugou8_not_whole_appdata(self):
        with mock.patch.object(kgg.os, "name", "nt"):
            with mock.patch.dict(os.environ, {
                "APPDATA": r"C:\Users\x\AppData\Roaming",
                "LOCALAPPDATA": r"C:\Users\x\AppData\Local",
            }):
                roots = kgg.default_roots()
        joined = [p.replace("\\", "/") for p in roots]
        self.assertTrue(any(p.endswith("KuGou8") for p in joined))
        self.assertNotIn(r"C:\Users\x\AppData\Roaming", roots)
        self.assertNotIn(r"C:\Users\x\AppData\Local", roots)

    def test_scan_skips_downloads(self):
        self.assertNotIn("~/Downloads", kgg.ROOTS)
        self.assertIn("steamapps", kgg.SKIP_DIRS)

    def test_missing_db_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            confdir = Path(tmp, "conf")
            with mock.patch.multiple(
                kgg,
                ROOTS=[tmp],
                MU_DIR=str(confdir),
                CONF=str(confdir / "kgg_db_path.txt"),
            ):
                self.assertIsNone(kgg.find_db())


class BrowserPathTests(unittest.TestCase):
    def test_windows_browsers_include_edge_qq_and_360(self):
        win = browser_cookies.BROWSERS["win32"]
        self.assertIn("QQBrowser", win["qqbrowser"])
        self.assertIn("Edge", win["edge"])
        self.assertIsInstance(win["360安全"], tuple)

    def test_linux_chrome_includes_snap_and_flatpak(self):
        roots = browser_cookies.BROWSERS["linux"]["chrome"]
        self.assertIn("~/snap/google-chrome/current/.config/google-chrome", roots)
        self.assertIn("~/.var/app/com.google.Chrome/config/google-chrome", roots)


class Win32CompatTests(unittest.TestCase):
    def test_parse_drop_strips_braces_and_file_url(self):
        self.assertEqual(
            win32compat.parse_drop_paths(["{C:/Users/a b/song.ncm}"]),
            [os.path.normpath("C:/Users/a b/song.ncm")],
        )
        self.assertEqual(
            win32compat.parse_drop_paths(["file:///C:/Users/a/song.ncm"]),
            [os.path.normpath("C:/Users/a/song.ncm")],
        )

    def test_docker_bind_uses_forward_slashes_on_windows(self):
        with mock.patch.object(win32compat.sys, "platform", "win32"):
            with mock.patch.object(os.path, "abspath", side_effect=lambda p: p):
                bind = win32compat.docker_bind(r"C:\Users\张三\lib.so", "/app/lib.so")
        self.assertEqual(bind, "C:/Users/张三/lib.so:/app/lib.so")

    def test_for_child_prefixes_long_windows_paths(self):
        long = "C:\\" + ("0123456789\\" * 24) + "song.ncm"
        with mock.patch.object(win32compat.sys, "platform", "win32"):
            with mock.patch.object(os.path, "abspath", return_value=long):
                p = win32compat.for_child("x")
        self.assertTrue(p.startswith("\\\\?\\"))

    def test_snapshot_sqlite_copies_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "KGMusicV3.db")
            Path(src).write_bytes(b"db")
            Path(src + "-wal").write_bytes(b"wal")
            out = win32compat.snapshot_sqlite(src, os.path.join(tmp, "snap"))
            self.assertEqual(Path(out).read_bytes(), b"db")
            self.assertEqual(Path(out + "-wal").read_bytes(), b"wal")

    def test_kgg_usable_db_passthrough_off_windows(self):
        if sys.platform == "win32":
            self.skipTest("non-windows passthrough")
        self.assertEqual(kgg.usable_db("/x/KGMusicV3.db"), "/x/KGMusicV3.db")


if __name__ == "__main__":
    unittest.main()
