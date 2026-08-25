#!/bin/bash
# 音乐解锁 Linux 通用安装包（AppImage，x86_64，各发行版可跑）
# 在源码仓库根目录：chmod +x packaging/build-linux.sh && ./packaging/build-linux.sh
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== 音乐解锁 Linux 构建 ==="
uname -m | grep -qx x86_64 || { echo "本脚本只打 x86_64 AppImage"; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少 $1"; exit 1; }; }
need git; need python3; need go; need cargo; need curl; need tar

VENV=/tmp/mu-linux-build-venv
echo "=== 1/7 Python 依赖 ==="
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
if ! python -c 'import PyInstaller, camoufox' >/dev/null 2>&1; then
  python -m pip install -U pip
  python -m pip install -r requirements-build.txt
  python -m pip install camoufox==0.5.5
fi

echo "=== 2/7 编译 um 引擎（Go） ==="
export GOPROXY=https://goproxy.cn,direct
if [ ! -x um ]; then
  rm -rf /tmp/um-cli
  git clone --depth 1 https://codeberg.org/TTsdzb/unlock-music-cli.git /tmp/um-cli
  (cd /tmp/um-cli && go build -o "$OLDPWD/um" ./cmd/um)
fi

echo "=== 3/7 编译 qmc-decoder 引擎（Rust） ==="
if [ ! -x qmc-decoder ]; then
  cargo build --release --manifest-path vendor/qmc-decoder/Cargo.toml
  cp vendor/qmc-decoder/target/release/qmc-decoder .
fi

echo "=== 4/7 下载运行时资产 + 打浏览器组件包 ==="
mkdir -p assets/bundled
if [ ! -s assets/wrapper-v2-image.tar.gz ]; then
  if [ -s "$HOME/.local/share/music-unlock/wrapper-v2-image.tar.gz" ]; then
    cp -f "$HOME/.local/share/music-unlock/wrapper-v2-image.tar.gz" assets/
  else
    gh release download runtime-assets -R WeiPengyu407/music-unlock \
      -p 'wrapper-v2-image.tar.gz' -D assets --clobber
  fi
fi
if [ ! -s assets/LIBS_VERSION.json ]; then
  if [ -s "$HOME/.local/share/music-unlock/LIBS_VERSION.json" ]; then
    cp -f "$HOME/.local/share/music-unlock/LIBS_VERSION.json" assets/
  else
    gh release download runtime-assets -R WeiPengyu407/music-unlock \
      -p 'LIBS_VERSION.json' -D assets --clobber
  fi
fi
if [ ! -f assets/bundled/browser-cache-camoufox.tar.gz ]; then
  python -c 'from pathlib import Path; import sys; p=Path.home()/".cache"/"ms-playwright";
print("cache", p); sys.exit(0 if any(p.glob("chromium_headless_shell-*")) else 1)' \
    || python -m patchright install chromium
  python -c 'from pathlib import Path; import sys; p=Path.home()/".cache"/"camoufox"; sys.exit(0 if p.is_dir() else 1)' \
    || python -m camoufox fetch
  python - <<'PY'
import os, sys, tarfile
from pathlib import Path
base = Path.home() / ".cache"
camoufox = base / "camoufox"
playwright = base / "ms-playwright"
if not camoufox.is_dir():
    raise SystemExit(f"camoufox cache not found: {camoufox}")
headless = next(iter(sorted(playwright.glob("chromium_headless_shell-*"))), None)
ffmpeg = next(iter(sorted(playwright.glob("ffmpeg-*"))), None)
if not headless or not ffmpeg:
    raise SystemExit(f"patchright cache incomplete: {playwright}")
output = Path("assets") / "bundled"
output.mkdir(parents=True, exist_ok=True)
with tarfile.open(output / "browser-cache-camoufox.tar.gz", "w:gz") as archive:
    archive.add(camoufox, arcname=camoufox.name)
with tarfile.open(output / "browser-cache-patchright.tar.gz", "w:gz") as archive:
    archive.add(headless, arcname=headless.name)
    archive.add(ffmpeg, arcname=ffmpeg.name)
print("packed", camoufox, headless, ffmpeg)
PY
fi

echo "=== 5/7 PyInstaller 冻结 ==="
pyinstaller --noconfirm --windowed --onedir --name music-unlock \
  --hidden-import apkmirror_fetch --hidden-import PIL._tkinter_finder \
  --collect-all ttkbootstrap --collect-all tkinterdnd2 \
  --collect-all gamdl --collect-all scrapling \
  --collect-all patchright --collect-all camoufox \
  --add-binary "um:." --add-binary "qmc-decoder:." \
  --add-data "assets:assets" \
  music_unlock.py

echo "=== 6/7 冻结包自检 ==="
dist/music-unlock/music-unlock --self-test

echo "=== 7/7 打 AppImage ==="
rm -rf AppDir
mkdir -p AppDir/usr/bin
cp -a dist/music-unlock AppDir/usr/bin/music-unlock-dir
cp packaging/AppRun AppDir/AppRun && chmod +x AppDir/AppRun
cp packaging/music-unlock.desktop packaging/music-unlock.png AppDir/
if [ ! -x /tmp/appimagetool ]; then
  gh release download continuous -R AppImage/appimagetool -p 'appimagetool-x86_64.AppImage' -D /tmp --clobber
  mv -f /tmp/appimagetool-x86_64.AppImage /tmp/appimagetool
  chmod +x /tmp/appimagetool
fi
if [ ! -s /tmp/runtime-x86_64 ]; then
  gh release download continuous -R AppImage/type2-runtime -p 'runtime-x86_64' -D /tmp --clobber
fi
export APPIMAGE_EXTRACT_AND_RUN=1
ARCH=x86_64 /tmp/appimagetool --runtime-file /tmp/runtime-x86_64 --comp zstd AppDir music-unlock-linux-x86_64.AppImage
echo ""
echo "完成！产物：$(pwd)/music-unlock-linux-x86_64.AppImage"
echo "各发行版：chmod +x 后双击或命令行运行即可。"
