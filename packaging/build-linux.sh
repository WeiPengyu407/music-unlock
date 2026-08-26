#!/bin/bash
# 音乐解锁 Linux 通用安装包（AppImage，x86_64，各发行版可跑）
# 在源码仓库根目录：chmod +x packaging/build-linux.sh && ./packaging/build-linux.sh
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== 音乐解锁 Linux 构建 ==="
case "$(uname -m)" in
  x86_64) AI_ARCH=x86_64; OUT_ARCH=x86_64; TAR=wrapper-v2-image.tar.gz ;;
  aarch64|arm64) AI_ARCH=aarch64; OUT_ARCH=arm64; TAR=wrapper-v2-image-arm64.tar.gz ;;
  *) echo "不支持的架构: $(uname -m)"; exit 1 ;;
esac
echo "架构: $OUT_ARCH"

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少 $1"; exit 1; }; }
need git; need python3; need go; need cargo; need curl; need tar; need gh

VENV=/tmp/mu-linux-build-venv
echo "=== 1/6 Python 依赖 ==="
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
if ! python -c 'import PyInstaller' >/dev/null 2>&1; then
  python -m pip install -U pip
  python -m pip install -r requirements-build.txt
fi

echo "=== 2/6 编译 um 引擎（Go） ==="
export GOPROXY=https://goproxy.cn,direct
if [ ! -x um ]; then
  rm -rf /tmp/um-cli
  git clone --depth 1 https://codeberg.org/TTsdzb/unlock-music-cli.git /tmp/um-cli
  (cd /tmp/um-cli && go build -o "$OLDPWD/um" ./cmd/um)
fi

echo "=== 3/6 编译 qmc-decoder 引擎（Rust） ==="
if [ ! -x qmc-decoder ]; then
  cargo build --release --manifest-path vendor/qmc-decoder/Cargo.toml
  cp vendor/qmc-decoder/target/release/qmc-decoder .
fi

echo "=== 4/6 下载运行时资产 ==="
mkdir -p assets
if [ ! -s "assets/$TAR" ]; then
  if [ -s "$HOME/.local/share/music-unlock/$TAR" ]; then
    cp -f "$HOME/.local/share/music-unlock/$TAR" assets/
  else
    gh release download runtime-assets -R WeiPengyu407/music-unlock \
      -p "$TAR" -D assets --clobber
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

echo "=== 5/6 PyInstaller 冻结 ==="
pyinstaller --noconfirm --windowed --onedir --name music-unlock \
  --hidden-import PIL._tkinter_finder \
  --collect-all ttkbootstrap --collect-all tkinterdnd2 \
  --collect-all gamdl \
  --add-binary "um:." --add-binary "qmc-decoder:." \
  --add-data "assets:assets" \
  music_unlock.py

echo "=== 6/6 冻结包自检 ==="
dist/music-unlock/music-unlock --self-test

echo "=== 打包 AppImage ==="
rm -rf AppDir
mkdir -p AppDir/usr/bin
cp -a dist/music-unlock AppDir/usr/bin/music-unlock-dir
cp packaging/AppRun AppDir/AppRun && chmod +x AppDir/AppRun
cp packaging/music-unlock.desktop packaging/music-unlock.png AppDir/
if [ ! -x /tmp/appimagetool ]; then
  gh release download continuous -R AppImage/appimagetool -p "appimagetool-${AI_ARCH}.AppImage" -D /tmp --clobber
  mv -f "/tmp/appimagetool-${AI_ARCH}.AppImage" /tmp/appimagetool
  chmod +x /tmp/appimagetool
fi
if [ ! -s "/tmp/runtime-${AI_ARCH}" ]; then
  gh release download continuous -R AppImage/type2-runtime -p "runtime-${AI_ARCH}" -D /tmp --clobber
fi
export APPIMAGE_EXTRACT_AND_RUN=1
ARCH="$AI_ARCH" /tmp/appimagetool --runtime-file "/tmp/runtime-${AI_ARCH}" --comp zstd AppDir "music-unlock-linux-${OUT_ARCH}.AppImage"
echo ""
echo "完成！产物：$(pwd)/music-unlock-linux-${OUT_ARCH}.AppImage"
