#!/bin/bash
# 音乐解锁 macOS 一键构建脚本（支持 Intel 和 M 系列，在源码仓库根目录里运行）
# 用法：chmod +x packaging/build-macos.sh && ./packaging/build-macos.sh
set -e
cd "$(dirname "$0")/.."
echo "=== 音乐解锁 macOS 构建 ==="

ARCH=$(uname -m)   # arm64 = M 系列；x86_64 = Intel
[ "$ARCH" = "arm64" ] && OUT_ARCH=arm64 || OUT_ARCH=x86_64
echo "芯片架构: $ARCH → 产物为 $OUT_ARCH 版"

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少 $1，正在用 Homebrew 安装..."; brew install "$2"; }; }
command -v brew >/dev/null 2>&1 || { echo "请先安装 Homebrew：https://brew.sh （一行命令），装完重跑本脚本"; exit 1; }
need git git
need python3 python@3.13
need go go
need cargo rust

echo "=== 1/6 安装 Python 依赖 ==="
python3 -m venv /tmp/mu-build-venv
source /tmp/mu-build-venv/bin/activate
pip install --upgrade pip
python -m pip install -r requirements-build.txt

echo "=== 2/6 编译 um 引擎（Go，走 Codeberg 镜像+goproxy.cn） ==="
export GOPROXY=https://goproxy.cn,direct
rm -rf /tmp/um-cli
git clone --depth 1 https://codeberg.org/TTsdzb/unlock-music-cli.git /tmp/um-cli
(cd /tmp/um-cli && go build -o "$OLDPWD/um" ./cmd/um)

echo "=== 3/6 编译 qmc-decoder 引擎（Rust） ==="
if [ ! -f ~/.cargo/config.toml ]; then
  mkdir -p ~/.cargo
  printf '[source.crates-io]\nreplace-with = "rsproxy-sparse"\n[source.rsproxy-sparse]\nregistry = "sparse+https://rsproxy.cn/index/"\n' > ~/.cargo/config.toml
fi
cargo build --release --manifest-path vendor/qmc-decoder/Cargo.toml
cp vendor/qmc-decoder/target/release/qmc-decoder .

echo "=== 4/6 PyInstaller 冻结 ==="
pyinstaller --noconfirm --windowed --onedir --name music-unlock \
  --hidden-import apkmirror_fetch --hidden-import PIL._tkinter_finder \
  --collect-all ttkbootstrap --collect-all tkinterdnd2 \
  --collect-all gamdl --collect-all scrapling --collect-all patchright --collect-all camoufox \
  --add-binary "um:." --add-binary "qmc-decoder:." \
  music_unlock.py

echo "=== 5/6 下载运行时资产 + 打浏览器组件包 ==="
mkdir -p dist/music-unlock/assets/bundled
BASE="https://github.com/WeiPengyu407/music-unlock/releases/download/runtime-assets"
TAR="wrapper-v2-image.tar.gz"
[ "$ARCH" = "arm64" ] && TAR="wrapper-v2-image-arm64.tar.gz"
curl -sfL "$BASE/$TAR" -o "dist/music-unlock/assets/$TAR"
curl -sfL "$BASE/LIBS_VERSION.json" -o dist/music-unlock/assets/LIBS_VERSION.json
python -m patchright install chromium
python -m camoufox fetch
CAMOU=~/Library/Caches/camoufox
PW=~/Library/Caches/ms-playwright
tar -czf dist/music-unlock/assets/bundled/browser-cache-camoufox.tar.gz -C ~/Library/Caches camoufox
SHELL_DIR=$(ls "$PW" | grep chromium_headless_shell | head -1)
FF_DIR=$(ls "$PW" | grep ffmpeg | head -1)
tar -czf dist/music-unlock/assets/bundled/browser-cache-patchright.tar.gz -C "$PW" "$SHELL_DIR" "$FF_DIR"

echo "=== 6/6 打 dmg ==="
mkdir -p dmg-root
# --windowed 在 macOS 会产出 .app；找不到就退回目录形式
cp -r dist/music-unlock.app dmg-root/ 2>/dev/null || cp -r dist/music-unlock dmg-root/
hdiutil create -volname 音乐解锁 -srcfolder dmg-root -ov -format UDZO "音乐解锁-macos-$OUT_ARCH.dmg"
echo ""
echo "完成！产物：$(pwd)/音乐解锁-macos-$OUT_ARCH.dmg"
echo "把这个 dmg 发回去就行。"
