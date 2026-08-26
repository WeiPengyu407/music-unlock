# 音乐解锁 Windows 一键构建脚本（在源码仓库根目录里运行）
# 用法：右键 → 使用 PowerShell 运行；若提示执行策略，先跑：
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\..
Write-Host "=== 音乐解锁 Windows 构建 ===" -ForegroundColor Cyan

function Need($cmd, $wingetId, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "缺少 $cmd，尝试用 winget 安装 $wingetId ..."
        winget install -e --id $wingetId --accept-source-agreements --accept-package-agreements
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "请先安装 $hint 再重跑本脚本" }
    }
}

Need git Git.Git "Git（https://git-scm.com）"
Need python Python.Python.3.13 "Python 3.13（python.org，勾选 Add to PATH）"
Need go GoLang.Go "Go（go.dev）"
Need cargo Rustlang.Rustup.MSVC "Rust（rustup.rs）"
if (-not (cargo --version 2>$null)) { rustup default stable }

Write-Host "=== 1/6 安装 Python 依赖 ==="
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

Write-Host "=== 2/6 编译 um 引擎（Go，走 Codeberg 镜像+goproxy.cn） ==="
$env:GOPROXY = 'https://goproxy.cn,direct'
if (Test-Path "$env:TEMP\um-cli") { Remove-Item -Recurse -Force "$env:TEMP\um-cli" }
git clone --depth 1 https://codeberg.org/TTsdzb/unlock-music-cli.git "$env:TEMP\um-cli"
Push-Location "$env:TEMP\um-cli"; go build -o "$OLDPWD\um.exe" ./cmd/um; Pop-Location

Write-Host "=== 3/6 编译 qmc-decoder 引擎（Rust） ==="
if (-not (Test-Path "$env:USERPROFILE\.cargo\config.toml")) {
    # crates.io 国内不稳，换 rsproxy 镜像
    "[source.crates-io]`nreplace-with = 'rsproxy-sparse'`n[source.rsproxy-sparse]`nregistry = 'sparse+https://rsproxy.cn/index/'" | Out-File -Encoding utf8 "$env:USERPROFILE\.cargo\config.toml"
}
cargo build --release --manifest-path vendor/qmc-decoder/Cargo.toml
Copy-Item vendor/qmc-decoder/target/release/qmc-decoder.exe .

Write-Host "=== 4/6 PyInstaller 冻结 ==="
pyinstaller --noconfirm --windowed --onedir --name music-unlock `
  --hidden-import PIL._tkinter_finder `
  --collect-all ttkbootstrap --collect-all tkinterdnd2 `
  --collect-all gamdl `
  --add-binary "um.exe;." --add-binary "qmc-decoder.exe;." `
  music_unlock.py

Write-Host "=== 5/6 下载运行时资产 ==="
New-Item -ItemType Directory -Force dist\music-unlock\assets | Out-Null
$base = "https://github.com/WeiPengyu407/music-unlock/releases/download/runtime-assets"
$tar = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'wrapper-v2-image-arm64.tar.gz' } else { 'wrapper-v2-image.tar.gz' }
Invoke-WebRequest "$base/$tar" -OutFile "dist\music-unlock\assets\$tar"
Invoke-WebRequest "$base/LIBS_VERSION.json" -OutFile dist\music-unlock\assets\LIBS_VERSION.json

Write-Host "=== 6/6 打便携包 ==="
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x86_64' }
Compress-Archive -Force -Path dist\music-unlock -DestinationPath "音乐解锁-windows-$arch-portable.zip"
Write-Host ""
Write-Host "完成！产物：$(Get-Location)\音乐解锁-windows-$arch-portable.zip" -ForegroundColor Green
Write-Host "把这个 zip 发回去就行。"
