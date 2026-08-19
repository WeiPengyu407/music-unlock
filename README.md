# 音乐解锁

加密音乐格式 → 普通音频，一拖一点即可。

## 两大核心卖点

### 1. 破解 QQ 音乐最新版加密（.mflac / .mgg，mmkv 密钥绑定）

市面上绝大多数工具对 QQ 音乐新版 musicex 格式已经失效——密钥和设备绑定，
离线根本解不开。本软件自研 ekey 链：**自动从本机浏览器提取 QQ 登录态**，
走 GetEVkey 把绑定密钥换成本地文件密钥，然后**纯本地解密**。
一次登录，长期有效；登录态获取失败会自动引导你去官网登录，点一下就好。

### 2. 破解 Apple Music（FairPlay 真解密，不是翻录）

把苹果官方安卓客户端的解密库拆出来（18 个零件，逐个 SHA-256 校验防篡改），
在本机 Docker 容器里搭一个"假手机"跑起来，gamdl 拉流后**真解密**落地成普通音频。
贴个链接就行，歌曲 / 专辑 / 歌单整批下。首次使用全自动装配，
你只用在最后登录一次 Apple ID。

---

## 其他支持格式

| 来源 | 格式 | 解密方式 | 需要登录？ |
|---|---|---|---|
| 网易云 | .ncm | um 引擎，本地秒解 | 不需要 |
| QQ 音乐（旧版） | .qmc0/.qmc2/.qmcflac/.qmcogg 等 | qmc-decoder，本地秒解 | 不需要 |
| QQ 音乐（新版 musicex） | .mflac/.mgg（带 mmkv 绑定） | 自研 ekey 链（见卖点 1） | 一次 QQ 登录 |
| 酷狗 / 酷我 / 虾米等 | .kgm/.kgma/.kgg/.kwm/.xm 等 | um 引擎，本地秒解 | 不需要 |
| Apple Music | 歌曲/专辑/歌单**链接** | wrapper-v2 真解密（见卖点 2） | 一次 Apple ID 登录（需订阅） |

界面风格：Fluent（Office 2024）。

## 下载安装

到 [Releases](../../releases) 页面下载对应系统的安装包：

- **Windows**：`音乐解锁-setup-windows-x86_64.exe`（安装版）或 `*-portable.zip`（便携版，解压即用）
- **macOS**：`音乐解锁-macos-x86_64.dmg`（x86_64；Apple Silicon 未经实测）
- **Linux**：`音乐解锁-x86_64.AppImage`（`chmod +x` 后直接运行）

所有安装包均由 GitHub Actions 自动构建（见 `.github/workflows/build.yml`），
构建日志公开可查。

## 使用方法

### 常规格式（网易云 / QQ 旧版 / 酷狗 / 酷我…）

把加密文件拖进窗口（或点【添加文件/文件夹】）→【开始转换】，
输出在同目录下的「已解锁」文件夹。全程离线，无任何登录。

### QQ 音乐新版（.mflac / .mgg）

1. 拖入文件，程序检测到新格式会弹窗提示需要 QQ 登录态
2. 点【导入QQ登录态】——自动从本机浏览器（Firefox / Chrome / Edge / Chromium / 360）
   提取 y.qq.com 的 cookie，成功即静默完成
3. 提取失败会自动打开 y.qq.com，并弹窗提示"请在**音乐文件来源方**官网上登录"；
   登录后点【我已登录，重新导入】即可
4. 凭据缓存于本机，之后解密同格式文件无需再登录

### Apple Music

1. 点【添加Apple链接】，粘贴歌曲 / 专辑 / 歌单链接（每行一个）
2. 首次使用会提示准备**特殊解密引擎**，点【立即准备】：
   全自动完成 安装 Docker → 导入内置解密镜像 → 自动拉取 Apple Music 安装包
   并拆取解密零件（逐个 SHA-256 校验）→ 启动解密容器
3. 随后弹窗登录 Apple ID（需订阅 Apple Music）。
   **凭据仅用于调用苹果解密服务，缓存在本机，不会上传他处**
4. 登录成功直接开始解密，输出在 `~/Music/已解锁`。
   之后再添加链接零打扰，直接解密

> 中国大陆网络环境下，自动拉取 APK 需要代理（默认 `127.0.0.1:7897`，
> 可用环境变量 `MUSIC_UNLOCK_PROXY` 修改）；拉取失败会退化为手动选择 APK 文件。

## 常见问题

**Q：Windows / macOS 上 Apple Music 功能的额外要求？**
需要自行安装并启动 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。
Linux 上由程序自动安装（pkexec 图形授权）。其余功能（网易云/QQ/酷狗等）开箱即用。

**Q：Apple ID 登录安全吗？**
账密只发送给本机 Docker 容器里的苹果官方解密组件（等价于在官方客户端里登录），
凭据文件只存在你自己的电脑上。支持双重认证（登录时填验证码栏）。

**Q：会花我的钱吗？**
不会。Apple Music 走的是订阅流媒体通道（与官方 App 的"下载到本地"同一接口），
不经过 iTunes Store 付费购买通道。

**Q：软件里包含苹果的代码吗？**
不包含。解密零件（18 个 `.so`）在使用者本机从 Apple Music 官方 APK 当场提取，
并逐个 SHA-256 校验（哈希表钉死，任何篡改都会被拒绝）。

## 免责声明

本工具仅供将**自己已购买或已订阅**的音乐内容转换为可自由播放的格式之用。
请勿用于任何侵犯版权的传播行为，使用后果由使用者自行承担。

## 从源码运行（开发者）

```bash
pip install ttkbootstrap tkinterdnd2 pycryptodome pillow gamdl "scrapling[all]"
# 引擎：um 见 git.unlock-music.dev/um/cli；qmc-decoder 见 vendor/qmc-decoder（cargo build --release）
python3 music_unlock.py
```

打包：`pyinstaller` 参数见 CI 工作流；`--self-test` 可验证打包产物完整性。

## 组件与许可

- [um](https://git.unlock-music.dev/um/cli)（unlock-music CLI, Go）
- qmc-decoder（Rust, GPL-3.0）：`vendor/qmc-decoder`（核心库）+ 本项目自写 CLI 封装
- [gamdl](https://github.com/glomatico/gamdl)（Apple Music 下载）、[wrapper-v2](https://github.com/glomatico/wrapper-v2)（FairPlay 运行时）
- [scrapling](https://github.com/D4Vinci/Scrapling)（反爬抓取）、ttkbootstrap、tkinterdnd2、pycryptodome

本项目以 GPL-3.0 开源（含 GPL-3.0 授权的 vendored 组件）。
