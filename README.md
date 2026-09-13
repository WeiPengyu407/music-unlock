<p align="center">
  <img src="packaging/music-unlock.png" width="96" alt="音乐解锁">
</p>

<h1 align="center">音乐解锁</h1>

<p align="center">
  把本地加密音乐文件转成普通音频的桌面程序。<br>
  <code>music-unlock</code>
</p>

<p align="center">
  <a href="https://github.com/WeiPengyu407/music-unlock/releases/latest"><img src="https://img.shields.io/github/v/release/WeiPengyu407/music-unlock" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/WeiPengyu407/music-unlock" alt="License"></a>
  <a href="https://github.com/WeiPengyu407/music-unlock/actions/workflows/test.yml"><img src="https://github.com/WeiPengyu407/music-unlock/actions/workflows/test.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue" alt="Platform">
</p>

把网易云、QQ 音乐、酷狗、酷我、咪咕等客户端里下下来的加密文件，拖进窗口即可转成普通音频；也支持粘贴 Apple Music 链接（需订阅）。界面是 Fluent 风格，主要给 Windows 使用，同时提供 macOS 和 Linux 安装包。

当前版本 **1.0.7**。安装包在 [Releases](https://github.com/WeiPengyu407/music-unlock/releases/latest)。

## 功能

- 拖入文件或文件夹，批量转换；结果写到同目录下的「已解锁」文件夹
- 网易云 `.ncm`、QQ 旧版 QMC、酷狗旧版 KGM、酷我 / 虾米、咪咕 `.mg3d`：本机解密，不用登录
- QQ 音乐新版 `.mflac` / `.mgg`（musicex）：从本机 QQ 音乐客户端或浏览器读取登录态，换出文件密钥后再本地解密
- 酷狗新版 `.kgg`：从酷狗 PC 客户端的本地数据库读取密钥
- Apple Music：粘贴歌曲 / 专辑 / 歌单链接，在本机 Docker 里调用官方解密组件（不是录屏翻录）
- 登录态只缓存在你自己的电脑上；能自动找到客户端数据时不会反复弹窗

## 支持的格式

| 来源 | 格式 | 说明 |
|---|---|---|
| 网易云 | `.ncm` | 本地解密 |
| QQ 音乐（旧版） | `.qmc0` / `.qmc2` / `.qmcflac` / `.qmcogg` 等 | 本地解密 |
| QQ 音乐（新版） | `.mflac` / `.mgg` | 需要一次 QQ 登录态 |
| 酷狗（旧版） | `.kgm` / `.kgma` | 本地解密 |
| 酷狗（新版） | `.kgg` | 需要一次酷狗 PC 登录 |
| 酷我 / 虾米等 | `.kwm` / `.xm` 等 | 本地解密 |
| 咪咕 | `.mg3d` | 本地解密 |
| Apple Music | 歌曲 / 专辑 / 歌单**链接** | 需要 Apple ID（须订阅）和 Docker |

## 安装

到 [Releases](https://github.com/WeiPengyu407/music-unlock/releases/latest) 下载对应系统的文件。

**Windows**（主要支持平台）

- 安装包：`music-unlock-setup-windows-x86_64.exe`（装到 `%LOCALAPPDATA%\音乐解锁`，不需要管理员）
- 便携版：`music-unlock-windows-x86_64-portable.zip`，解压即用
- ARM 设备（部分 Surface 等）用文件名里的 `arm64`

**macOS**

- Apple 芯片：`music-unlock-macos-arm64.dmg`
- Intel：`music-unlock-macos-x86_64.dmg`

**Linux**

- `music-unlock-linux-x86_64.AppImage` 或 `music-unlock-linux-arm64.AppImage`
- `chmod +x` 之后直接运行

网易云 / QQ / 酷狗 / 酷我 / 咪咕开箱即用。Apple Music 在 Windows 和 macOS 上需要先安装并启动 [Docker Desktop](https://www.docker.com/products/docker-desktop/)；Linux 上若本机还没有 Docker，程序可以走发行版包管理器安装（需图形授权）。

## 使用

### 普通加密文件

拖进窗口，或点「添加文件 / 文件夹」，再点「开始转换」。输出在源文件同目录的「已解锁」里。

### QQ 音乐新版（`.mflac` / `.mgg`）

1. 拖入文件后，若需要登录态会弹窗
2. 点「导入 QQ 登录态」：Windows 先读 QQ 音乐客户端，再读 Edge / Chrome / QQ 浏览器 / 360
3. 都没有则先打开 QQ 音乐并登录，再点「我已登录，重新导入」
4. 凭据缓存在本机，之后同格式不用再登录

### 酷狗新版（`.kgg`）

1. 拖入后会先在本机静默查找酷狗 PC 客户端数据，找到即直接解
2. 找不到才弹窗，点「导入酷狗登录态」。Windows 会找 `%APPDATA%\KuGou8\KGMusicV3.db`
3. 仍没有则打开酷狗音乐 PC 版并登录，再点「我已登录，重新导入」；实在找不到再手动选客户端目录里的 `KGMusicV3.db`
4. 数据库路径会记住

### Apple Music

1. 点「添加 Apple 链接」，每行一个歌曲 / 专辑 / 歌单链接
2. 第一次会提示准备解密环境。点「立即准备」后，程序导入内置镜像、拉取 Apple Music 安装包并拆出解密零件（逐个 SHA-256 校验），再启动容器
3. 用你的 Apple ID 登录（须订阅 Apple Music）。账密只发给本机容器里的官方解密组件，支持双重认证
4. 输出在「音乐 / 已解锁」。之后再贴链接一般不再打扰

安装包里的镜像从 GitHub Release 拉取（国内会走镜像）。失败时可改为手动选择 APK。

## 常见问题

**Windows / macOS 上 Apple Music 不能用？**  
先安装并启动 Docker Desktop。其余格式不依赖 Docker。

**Apple ID 会不会被上传？**  
不会。账密只送到本机 Docker 容器，凭据文件也只写在你自己的电脑上。

**会不会产生额外扣费？**  
不会。走的是订阅流媒体通道，和官方 App 的「下载到本地」同一类接口，不经过 iTunes Store 购买。

**安装包里有没有苹果的代码？**  
没有。18 个解密零件（`.so`）在你本机从 Apple Music 官方 APK 提取，哈希表写死，对不上就拒绝。

## 从源码运行

需要 Python 3.13、Go、Rust。图形界面仍是 Python；仓库里另有一套实验性 Rust CLI（`crates/`），尚未覆盖 QQ 登录态和 Apple 链。

```bash
python -m pip install -r requirements-build.txt

# um 引擎（Go）
git clone --depth 1 https://codeberg.org/TTsdzb/unlock-music-cli.git /tmp/um-cli
(cd /tmp/um-cli && go build -o "$OLDPWD/um" ./cmd/um)

# qmc-decoder（Rust，产物在仓库根 target/release/）
cargo build --release -p qmc-decoder

python3 music_unlock.py
```

测试：

```bash
python -m unittest discover -s tests -v
cargo test --workspace
```

打包由 GitHub Actions 完成（`.github/workflows/build.yml`）。本机也可以跑：

- Windows：`packaging/build-windows.ps1`
- macOS：`packaging/build-macos.sh`
- Linux：`packaging/build-linux.sh`

冻结后的程序可用 `--self-test` 检查引擎和运行时资产是否打进包内。

## 组件

本程序是交互壳，解密由下列引擎完成：

- [um](https://git.unlock-music.dev/um/cli)（unlock-music CLI，Go）
- qmc-decoder（Rust，GPL-3.0）：`vendor/qmc-decoder`
- 本仓库的 QQ ekey 链、酷狗 `.kgg` 定位、咪咕 `.mg3d`
- [gamdl](https://github.com/glomatico/gamdl)、[wrapper-v2](https://github.com/glomatico/wrapper-v2)（Apple Music）
- ttkbootstrap、tkinterdnd2、pycryptodome

## 许可证

[GPL-3.0](LICENSE)。vendored 的 qmc-decoder 同样是 GPL-3.0。

## 免责声明

本工具仅供将**自己已购买或已订阅**的音乐内容转换为可自由播放的格式之用。请勿用于任何侵犯版权的传播行为。使用本软件的一切后果由使用者自行承担。

对本软件的功能说明、使用范围及本声明的理解，如有争议，**最终解释权归软件作者 WeiPengyu407 所有**。
