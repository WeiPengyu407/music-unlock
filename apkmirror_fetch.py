#!/usr/bin/env python3
"""用 scrapling 隐身浏览器穿透 APKMirror 反爬，取 Apple Music 3.6.0-beta-1109
(arm64-v8a + x86_64) 变体的真实下载直链。
两种用法：
  开发模式  —— 子进程: apkmirror_fetch.py [proxy_url]，直链打印到 stdout
  冻结模式  —— 应用内: from apkmirror_fetch import get_direct_url"""
import re
import sys


def get_direct_url(proxy=None):
    from scrapling.fetchers import StealthySession

    variant = ("https://www.apkmirror.com/apk/apple/apple-music/"
               "apple-music-3-6-0-beta-release/apple-music-3-6-0-beta-4-android-apk-download/")
    kw = {"headless": True}
    if proxy:
        kw["proxy"] = proxy
    with StealthySession(**kw) as s:
        # 变体页 → 拿 ?key= 中间页
        v = s.fetch(variant, google_search=False)
        m = re.search(r'href="([^"]*download/\?key=[^"]*)"',
                      v.body if isinstance(v.body, str) else v.body.decode())
        if not m:
            raise RuntimeError("no key link")
        key_url = m.group(1)
        if key_url.startswith("/"):
            key_url = "https://www.apkmirror.com" + key_url
        # 中间页 → 拿 download.php 直链
        d = s.fetch(key_url, google_search=False)
        dh = d.body if isinstance(d.body, str) else d.body.decode()
        m2 = re.search(r"download\.php\?id=\d+&amp;key=[0-9a-f]+", dh)
        if not m2:
            raise RuntimeError("no direct link")
        return ("https://www.apkmirror.com/wp-content/themes/APKMirror/"
                + m2.group(0).replace("&amp;", "&"))


def main():
    proxy = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    try:
        print(get_direct_url(proxy))
    except Exception as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
