import os
import struct
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
import music_unlock
import qmc_ekey


class FileDetectionTests(unittest.TestCase):
    def test_only_known_encrypted_extensions_are_accepted(self):
        self.assertTrue(music_unlock.is_music_file("song.ncm"))
        self.assertTrue(music_unlock.is_music_file("song.mflac0"))
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
                (False, "downloader", "下载器 gamdl 未安装"),
            )

    def test_dynamic_patchright_cache_version_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            camoufox = Path(tmp, "camoufox")
            playwright = Path(tmp, "ms-playwright")
            camoufox.mkdir()
            Path(playwright, "chromium_headless_shell-9999").mkdir(parents=True)
            with mock.patch.multiple(
                apple_music,
                FROZEN=True,
                _cache_dirs=mock.Mock(
                    return_value=(str(camoufox), str(playwright))),
            ):
                apple_music.ensure_scrapling()

            self.assertTrue(
                Path(playwright, ".installed-by-music-unlock").exists())


if __name__ == "__main__":
    unittest.main()
