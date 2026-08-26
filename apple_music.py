#!/usr/bin/env python3
"""Apple Music 链封装：wrapper-v2 容器(假安卓跑苹果官方解密库) + gamdl 下载。
对外只暴露三件事：环境是否就绪、是否已登录、登录、下载。"""
import http.client
import gzip
import json
import os
import re
import subprocess
import sys

WRAPPER_HOST = "127.0.0.1"
WRAPPER_PORT = 80
CONTAINER = "wrapper-v2"

FROZEN = getattr(sys, "frozen", False)  # PyInstaller 冻结模式：gamdl 已打进 App，不再建 venv

# 打包后（PyInstaller）的内置资产目录；开发时回退到脚本目录
BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ASSETS_SRC = os.path.join(BUNDLE_DIR, "assets")


def _venv_tool(venv, name):
    exe = f"{name}.exe" if sys.platform == "win32" else name
    sub = "Scripts" if sys.platform == "win32" else "bin"
    return os.path.join(venv, sub, exe)


def _mp_child(mod, args, q):
    """冻结模式子进程入口（spawn 要求模块级可 pickle，不能是闭包）。"""
    import runpy
    import sys as _s
    _s.argv = [mod, *args]

    class _W:
        def write(self, t):
            if isinstance(t, bytes):  # 有些库直接往 stdout 写 bytes
                t = t.decode("utf-8", "replace")
            q.put(t)

        def flush(self):
            pass

    _s.stdout = _s.stderr = _W()
    try:
        runpy.run_module(mod, run_name="__main__")
        q.put(("__exit__", 0))
    except SystemExit as e:
        q.put(("__exit__", e.code if isinstance(e.code, int) else 1))
    except Exception as e:
        q.put(str(e))
        q.put(("__exit__", 1))


def _module_run(mod, args, on_line=None):
    """冻结模式下在子进程里跑一个已打包的 python 模块（等价 python -m mod args）。
    逐行回调输出，返回 (退出码, 末尾若干行)。"""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_mp_child, args=(mod, args, q))
    p.start()
    tail, buf, rc = [], "", None
    while rc is None:
        try:
            item = q.get(timeout=600)
        except Exception:
            break
        if isinstance(item, tuple) and item[0] == "__exit__":
            rc = item[1]
            break
        buf += item
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if line:
                tail.append(line)
                tail = tail[-20:]
                if on_line:
                    on_line(line)
    p.join(timeout=30)
    if p.is_alive():
        p.terminate()
    return (rc if rc is not None else 1), tail


class WrapperError(Exception):
    pass


def seed_assets(progress_cb=None):
    """首跑播种：把 bundle 里的内置资产（镜像包/离线 wheel）
    落到运行时目录 MU_DIR。已存在的跳过；开发环境（无 assets 目录）直接跳过。"""
    cb = progress_cb or (lambda t: None)
    if not os.path.isdir(ASSETS_SRC):
        return
    os.makedirs(MU_DIR, exist_ok=True)
    for item in ("wrapper-v2-image.tar.gz", "wrapper-v2-image-arm64.tar.gz", "wheels"):
        src = os.path.join(ASSETS_SRC, item)
        dst = os.path.join(MU_DIR, item)
        if os.path.exists(src) and not os.path.exists(dst):
            cb("首次运行：安置内置组件…")
            if os.path.isdir(src):
                import shutil as _sh
                _sh.copytree(src, dst)
            else:
                import shutil as _sh
                _sh.copy2(src, dst)


def _req(method, path, payload=None, timeout=15):
    conn = http.client.HTTPConnection(WRAPPER_HOST, WRAPPER_PORT, timeout=timeout)
    try:
        body = json.dumps(payload) if payload is not None else None
        conn.request(method, path, body=body,
                     headers={"Content-Type": "application/json"} if body else {})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8", "replace"))
        if resp.status >= 400:
            raise WrapperError(data.get("detail") or data.get("error") or f"HTTP {resp.status}")
        return data
    except (OSError, http.client.HTTPException) as e:
        raise WrapperError(f"wrapper 不可达：{e}")
    finally:
        conn.close()


def _try_start_container():
    """容器没起就拉一把。用户在 docker 组里则免 sudo；不在也静默失败，交给上层报错。"""
    for cmd in (["docker", "start", CONTAINER],
                ["sudo", "-n", "docker", "start", CONTAINER]):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            if r.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def wrapper_up():
    """wrapper 服务是否可用；不可用会先尝试启动容器再复查一次。"""
    for attempt in range(2):
        try:
            d = _req("GET", "/health", timeout=8)
            if d.get("status") == "ok":
                return True
        except WrapperError:
            pass
        if attempt == 0:
            _try_start_container()
    return False


def playback_ready():
    try:
        return bool(_req("GET", "/me")["runtime"]["playback_ready"])
    except (WrapperError, KeyError):
        return False


def is_logged_in():
    try:
        return _req("GET", "/me")["auth"]["state"] == "authenticated"
    except (WrapperError, KeyError):
        return False


def login(apple_id, password, code=None):
    """登录 Apple ID（需 Apple Music 订阅）。成功返回 storefront，失败抛 WrapperError。"""
    payload = {"apple_id": apple_id.strip(), "password": password}
    if code:
        payload["code"] = code.strip()
    d = _req("POST", "/login", payload, timeout=60)
    if d.get("state") != "authenticated":
        raise WrapperError(d.get("state") or "登录状态异常")
    return d.get("storefront", "")


def is_apple_url(text):
    return text.strip().lower().startswith(("https://music.apple.com/", "http://music.apple.com/"))


def check_chain():
    """按依赖顺序走查整条链：容器服务 → 解密引擎 → 下载器 → 登录态。"""
    if not wrapper_up():
        return False, "container", "wrapper 服务未运行（容器 wrapper-v2 未启动）"
    if not playback_ready():
        return False, "engine", "解密引擎未就绪（playback_ready=false）"
    if not (FROZEN or os.path.exists(GAMDL)):
        return False, "downloader", "下载器 gamdl 未安装"
    if not is_logged_in():
        return False, "auth", "Apple ID 未登录或会话已失效"
    return True, None, ""


def download(url, outdir, progress_cb=None):
    """gamdl 经 wrapper 解密下载，返回 (成功与否, 失败原因)。输出为普通音频文件。
    progress_cb 可选，逐曲目回调进度文本（苹果链是网络拉流，耗时远长于本地解密）。
    冻结模式：gamdl 已打进 App，子进程跑模块；开发模式：调 venv 里的 CLI。"""
    if not FROZEN and not os.path.exists(GAMDL):
        return False, "缺少 gamdl"
    os.makedirs(outdir, exist_ok=True)
    args = ["--use-wrapper",
            "--wrapper-url", f"http://{WRAPPER_HOST}:{WRAPPER_PORT}",
            "--wrapper-decrypt-host", WRAPPER_HOST,
            "--wrapper-decrypt-port", "10020",
            "--song-codec-priority", "alac,aac",  # 无损优先，拿不到无损才退 AAC
            "--output-path", outdir, url]

    def on_line(line):
        if progress_cb:
            m = re.search(r"\[Track\s+\d+/\d+\s*\]\s*(.*)", line)
            if m:
                progress_cb(m.group(1)[:60])

    if FROZEN:
        rc, tail = _module_run("gamdl", args, on_line)
    else:
        p = subprocess.Popen([GAMDL, *args],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail = []
        ansi = re.compile(r"\x1b\[[0-9;]*m")
        for line in p.stdout:
            line = ansi.sub("", line).strip()
            if not line:
                continue
            tail.append(line)
            tail = tail[-20:]
            on_line(line)
        p.wait(timeout=1800)
        rc = p.returncode
    if rc == 0:
        return True, ""
    return False, (tail[-1][:80] if tail else "下载失败")


# =====================================================================
# 首次装配（provision）：APK 从 GitHub Release（国内镜像）拉，拆件验哈希。
# 内置物：预构建 Docker 镜像（只含 AOSP 系统件 + 解密程序，无苹果代码）、
#         gamdl 离线 wheel 包。安装包本身不含苹果代码。
# 当场搞：下载 APK → 拆 18 个 .so → 哈希校验 → 挂载进容器。
# =====================================================================
import hashlib
import shutil
import zipfile

def _target_arch():
    """容器/零件架构：Apple Silicon（及其他 arm64 主机）用 arm64 原生镜像，
    Docker Desktop 原生速度运行；x86_64 主机用 x86_64 镜像。"""
    import platform
    return "arm64-v8a" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"


def _image_tag():
    return "wrapper-v2:arm64" if _target_arch() == "arm64-v8a" else "wrapper-v2:latest"


if sys.platform == "win32":
    _BASE = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
elif sys.platform == "darwin":
    _BASE = os.path.expanduser("~/Library/Application Support")
else:
    _BASE = os.path.expanduser("~/.local/share")
MU_DIR = os.path.join(_BASE, "music-unlock")
WRAP_DIR = os.path.join(MU_DIR, "wrapper-v2")
LIBS_DIR = os.path.join(MU_DIR, "apple-libs")
DATA_DIR = os.path.join(WRAP_DIR, "data")
WHEELS_DIR = os.path.join(MU_DIR, "wheels")
IMAGE_TAR = os.path.join(
    MU_DIR,
    "wrapper-v2-image-arm64.tar.gz" if _target_arch() == "arm64-v8a"
    else "wrapper-v2-image.tar.gz")
GAMDL_VENV = os.path.join(_BASE, "gamdl-venv")
GAMDL = _venv_tool(GAMDL_VENV, "gamdl")
APK_CACHE = os.path.join(MU_DIR, "apple-music-3.6.0-beta.apkm")
_APK_GITHUB = (
    "https://github.com/WeiPengyu407/music-unlock/releases/download/"
    "runtime-assets/apple-music-3.6.0-beta.apkm")
# 国内 GitHub 文件加速，用户不用自备代理。
_APK_MIRRORS = (
    "https://ghfast.top/",
    "https://gh-proxy.com/",
    "https://ghproxy.net/",
)


def _apk_urls():
    return [p + _APK_GITHUB for p in _APK_MIRRORS] + [_APK_GITHUB]


def fetch_apk(progress_cb=None):
    """从 GitHub Release（国内镜像优先）拉 Apple Music 安装包。
    安全性不靠下载源：拆件后 18 个 .so 逐个对 SHA-256，对不上就拒。"""
    cb = progress_cb or (lambda t: None)
    if os.path.exists(APK_CACHE) and os.path.getsize(APK_CACHE) >= 50_000_000:
        return APK_CACHE
    cb("下载 Apple Music 安装包（约 84MB）…")
    os.makedirs(MU_DIR, exist_ok=True)
    tmp = APK_CACHE + ".part"
    try:
        for url in _apk_urls():
            if os.path.exists(tmp):
                os.remove(tmp)
            r = subprocess.run(
                ["curl", "-fL", "-m", "600", "--retry", "2", "-o", tmp, url],
                capture_output=True, text=True, timeout=660)
            if (r.returncode == 0 and os.path.exists(tmp)
                    and os.path.getsize(tmp) >= 50_000_000):
                os.replace(tmp, APK_CACHE)
                return APK_CACHE
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    raise WrapperError("安装包下载失败")


def _docker(*args, timeout=120, capture=True):
    """docker 命令：优先直接调（用户在 docker 组），失败退到 sudo -n。返回 CompletedProcess。"""
    last = None
    for cmd in (["docker", *args], ["sudo", "-n", "docker", *args]):
        try:
            r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
            if r.returncode == 0:
                return r
            last = r
        except (OSError, subprocess.TimeoutExpired) as e:
            last = e
    raise WrapperError(f"docker {' '.join(args)} 失败："
                       f"{getattr(last, 'stderr', '') or last}")


def _pkexec(*args):
    """需要授权的系统操作（弹 polkit 图形授权框）。pkexec 要绝对路径。"""
    name = args[0]
    if not name.startswith("/"):
        for d in os.environ.get("PATH", "").split(":") + ["/usr/sbin", "/sbin", "/usr/bin", "/bin"]:
            p = os.path.join(d, name)
            if os.path.exists(p):
                name = p
                break
    r = subprocess.run(["pkexec", name, *args[1:]], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise WrapperError(f"需要授权的系统操作失败：{' '.join(args)}（{r.stderr.strip()[:60]}）")


def _install_docker_linux():
    """用当前发行版已有的包管理器安装 Docker。"""
    managers = (
        ("zypper", ("--non-interactive", "install", "docker")),
        ("apt-get", ("install", "-y", "docker.io")),
        ("dnf", ("install", "-y", "docker")),
        ("yum", ("install", "-y", "docker")),
        ("pacman", ("-S", "--noconfirm", "docker")),
    )
    for manager, args in managers:
        if shutil.which(manager):
            if manager == "apt-get":
                _pkexec("apt-get", "update")
            _pkexec(manager, *args)
            return
    raise WrapperError("未找到支持的包管理器，请先安装 Docker 后重试")


def _current_username():
    """返回当前进程的真实系统用户名，不依赖可被覆盖的 USER 环境变量。"""
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError, OSError):
        import getpass
        return getpass.getuser()


def _load_docker_image():
    """不经过 shell 管道，把 gzip 镜像流直接交给 docker load。"""
    last = None
    for cmd in (["docker", "load"], ["sudo", "-n", "docker", "load"]):
        process = None
        try:
            process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with gzip.open(IMAGE_TAR, "rb") as image:
                shutil.copyfileobj(image, process.stdin, length=1024 * 1024)
            process.stdin.close()
            process.stdin = None
            _stdout, stderr = process.communicate(timeout=900)
            if process.returncode == 0:
                return
            last = stderr.decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired) as exc:
            if process is not None and process.poll() is None:
                process.kill()
            last = str(exc)
    raise WrapperError("导入镜像失败：" + (last or "未知错误")[:80])


def _expected_libs():
    """零件哈希表：开发环境在 wrapper 源码目录，打包环境在 bundle 资产里。
    按主机架构取 x86_64 或 arm64-v8a 分组。"""
    for p in (os.path.join(WRAP_DIR, "LIBS_VERSION.json"),
              os.path.join(ASSETS_SRC, "LIBS_VERSION.json")):
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)["libs"][_target_arch()]
    raise WrapperError("缺少零件哈希表 LIBS_VERSION.json")


def libs_staged():
    if not os.path.isdir(LIBS_DIR):
        return False
    try:
        return all(os.path.exists(os.path.join(LIBS_DIR, n)) for n in _expected_libs())
    except Exception:
        return False


def stage_libs_from_apk(apk_path):
    """从 APK/APKM 拆出本机架构的 18 个苹果 .so，逐字节对哈希（防篡改），落位 LIBS_DIR。"""
    expected = _expected_libs()
    arch_token = "arm64" if _target_arch() == "arm64-v8a" else "x86_64"
    got = {}

    def harvest(zf, prefix=""):
        for name in zf.namelist():
            base = name.rsplit("/", 1)[-1]
            if base in expected and (f"lib/{arch_token}" in name or prefix):
                got[base] = zf.read(name)

    try:
        with zipfile.ZipFile(apk_path) as z:
            names = z.namelist()
            if any(n.endswith(".apk") for n in names):  # APKM 套娃包
                inner = [n for n in names if arch_token in n and n.endswith(".apk")]
                if not inner:
                    raise WrapperError(f"APK 包里没有 {arch_token} 架构的零件（换个通用包）")
                import io
                with zipfile.ZipFile(io.BytesIO(z.read(inner[0]))) as z2:
                    harvest(z2)
            else:
                harvest(z)
    except zipfile.BadZipFile:
        raise WrapperError("不是有效的 APK/APKM 文件")

    missing = [n for n in expected if n not in got]
    if missing:
        raise WrapperError(f"APK 里缺 {len(missing)} 个零件，版本可能不对（需 3.6.0-beta-1109）")
    bad = [n for n, data in got.items()
           if hashlib.sha256(data).hexdigest() != expected[n]]
    if bad:
        raise WrapperError(f"{len(bad)} 个零件哈希对不上，包被改过或版本不对，已拒绝")
    os.makedirs(LIBS_DIR, exist_ok=True)
    for n, data in got.items():
        with open(os.path.join(LIBS_DIR, n), "wb") as f:
            f.write(data)
    return len(got)


def provisioned():
    """特殊解密引擎是否已装配好。"""
    # 快路径：引擎已经在跑就不必碰 docker CLI
    #（当前 GUI 会话可能还没继承 docker 组，但容器开着就够用）
    gamdl_ok = FROZEN or os.path.exists(GAMDL)
    try:
        if gamdl_ok and wrapper_up() and playback_ready():
            return True
    except Exception:
        pass
    # 慢路径：镜像 + 零件 + 下载器都在就算装配过（容器随时可拉起）
    if not (libs_staged() and gamdl_ok):
        return False
    try:
        return bool(_docker("images", "-q", _image_tag(), timeout=15).stdout.strip())
    except WrapperError:
        return False


def provision(progress_cb, apk_path=None):
    """全自动装配特殊解密引擎。每步幂等：已就绪就跳过。
    progress_cb 收进度文本；需要 APK 而没给时抛 WrapperError("NEED_APK")。"""
    cb = progress_cb or (lambda t: None)

    # 快路径：引擎已经在跑，什么系统操作都不用做
    if (FROZEN or os.path.exists(GAMDL)) and wrapper_up() and playback_ready():
        cb("特殊解密引擎已就绪")
        return

    cb("检查 Docker…")
    if sys.platform != "linux":
        # Windows/macOS：Docker Desktop 需用户自行安装启动
        try:
            _docker("info", timeout=15)
        except WrapperError:
            raise WrapperError("未检测到运行中的 Docker。请安装并启动 Docker Desktop 后重试")
    else:
        if not shutil.which("docker"):
            cb("安装 Docker（需要授权）…")
            _install_docker_linux()
        try:
            _docker("info", timeout=15)
        except WrapperError:
            cb("启动 Docker 服务（需要授权）…")
            _pkexec("systemctl", "enable", "--now", "docker")
            _pkexec("usermod", "-aG", "docker", _current_username())
            try:
                _docker("info", timeout=15)
            except WrapperError:
                raise WrapperError("Docker 已配置好，但 docker 权限要注销重新登录后才生效，请重登后再试")

    cb("检查解密引擎镜像…")
    try:
        have_image = bool(_docker("images", "-q", _image_tag(), timeout=15).stdout.strip())
    except WrapperError:
        have_image = False
    if not have_image:
        if not os.path.exists(IMAGE_TAR):
            raise WrapperError(f"缺少内置镜像包 {IMAGE_TAR}")
        cb("导入内置解密引擎镜像（约 1 分钟）…")
        _load_docker_image()

    cb("检查苹果解密零件…")
    if not libs_staged():
        if not apk_path:
            try:
                apk_path = fetch_apk(cb)
            except WrapperError:
                raise WrapperError("NEED_APK")  # 自动拉取失败，交给 UI 兜底手动选择
        cb("从 APK 拆取解密零件并校验…")
        n = stage_libs_from_apk(apk_path)
        cb(f"{n} 个零件校验通过")

    cb("启动解密容器…")
    ps = _docker("ps", "-a", "--format", "{{.Names}}", timeout=15).stdout.split()
    if CONTAINER in ps:
        _docker("start", CONTAINER, timeout=60)
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        # 苹果零件逐文件挂载（而不是整个 lib64 目录），否则会遮住镜像里的
        # AOSP 系统件（libc.so 等），daemon 会起不来。
        cmd = ["run", "-d", "--name", CONTAINER, "--privileged",
               "--restart", "unless-stopped",
               "-p", "80:80", "-p", "10020:10020"]
        for name in _expected_libs():
            cmd += ["-v", f"{os.path.join(LIBS_DIR, name)}:/app/rootfs/system/lib64/{name}"]
        cmd += ["-v", f"{DATA_DIR}:/app/rootfs/data/data/com.apple.android.music/files",
                _image_tag()]
        _docker(*cmd, timeout=60)

    cb("检查下载器 gamdl…")
    if not FROZEN and not os.path.exists(GAMDL):  # 冻结模式下 gamdl 已打进 App
        cb("安装下载器 gamdl（离线包）…")
        subprocess.run(["python3", "-m", "venv", GAMDL_VENV],
                       capture_output=True, timeout=300)
        pip = _venv_tool(GAMDL_VENV, "pip")
        r = subprocess.run([pip, "install", "--no-index", "--find-links", WHEELS_DIR, "gamdl"],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            r = subprocess.run([pip, "install", "gamdl"],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                raise WrapperError("gamdl 安装失败：" + r.stderr.strip()[-80:])

    cb("等待解密引擎自检…")
    import time
    for _ in range(15):
        if wrapper_up() and playback_ready():
            cb("特殊解密引擎准备完成")
            return
        time.sleep(2)
    raise WrapperError("引擎自检超时（playback_ready 未就绪）")
