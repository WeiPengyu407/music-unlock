#!/usr/bin/env python3
"""音乐解锁：加密音乐格式(ncm/qmc*/kgm/kgma/kwm/xm等)批量转普通音频，另支持 Apple Music 链接下载。
解密引擎：um + qmc-decoder + 自研 ekey 链 + wrapper-v2/gamdl 苹果链，本程序是交互壳。UI 风格: Fluent (Office 2024)。

苹果链交互（按用户设计）：
- 首次添加 Apple 链接（特殊解密引擎未装配）→ 弹窗【立即准备】【稍后再说】。
  稍后再说 = 跳过并标记解密失败；立即准备 = 全自动装配（组件全内置，
  唯一需当场提供的是 Apple Music 安装包，用于拆取解密零件）→ 弹窗索取
  Apple ID 和密码（注明用处）→ 直接开始解密。
- 非首次（引擎已在）→ 不打扰，直接解密；登录态失效才弹登录窗。"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _p in __import__("glob").glob(os.path.expanduser("~/.local/share/mu-venv/lib/python*/site-packages")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ttkbootstrap as ttk
from ttkbootstrap.constants import PRIMARY, SECONDARY, OUTLINE

_BUNDLE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _engine(name):
    """解密引擎二进制：打包后优先用 bundle 内置的，否则回退 ~/.local/bin。"""
    exe = name + (".exe" if sys.platform == "win32" else "")
    for p in (os.path.join(_BUNDLE, exe), os.path.expanduser(os.path.join("~/.local/bin", exe))):
        if os.path.exists(p):
            return p
    return os.path.expanduser(os.path.join("~/.local/bin", exe))


UM = _engine("um")
QMC = _engine("qmc-decoder")
OUT_NAME = "已解锁"

# ---- Fluent (Office 2024) 配色 ----
BG = "#FFFFFF"
SURFACE = "#F5F5F5"
ACCENT = "#0F6CBD"
ACCENT_HOVER = "#115EA3"
TEXT = "#1B1B1B"
MUTED = "#616161"
BORDER = "#E1DFDD"
FONT = ("Microsoft YaHei UI", "Noto Sans CJK SC")

ENCRYPTED_EXTS = {
    ".ncm", ".qmc0", ".qmc2", ".qmc3", ".qmc4", ".qmc6", ".qmc8", ".qmcflac", ".qmcogg",
    ".kgm", ".kgma", ".kgg", ".kwm", ".xm", ".x2m", ".x3m", ".tkm",
    ".tm0", ".tm2", ".tm3", ".tm6", ".vpr", ".mmp4",
}
ENCRYPTED_PREFIXES = (".mflac", ".mgg", ".bkc", ".kgm")


def is_music_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in ENCRYPTED_EXTS or ext == "" or any(ext.startswith(p) for p in ENCRYPTED_PREFIXES)


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in files:
                    fp = os.path.join(root, f)
                    if is_music_file(fp):
                        out.append((fp, os.path.relpath(fp, p)))
        elif is_music_file(p):
            out.append((p, os.path.basename(p)))
    return out


def _font(size=10, weight="normal"):
    return (FONT[0], size, weight) if weight != "normal" else (FONT[0], size)


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="cosmo")
        self.title("音乐解锁")
        self.geometry("680x520")
        self.minsize(560, 420)
        self.configure(bg=BG)
        self.items = []
        self.outdir = None
        self._qq_prompted = False
        self._apple_prompted = False

        style = ttk.Style()
        style.configure("App.TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE, borderwidth=1, relief="solid")
        style.configure("App.TLabel", background=BG, foreground=TEXT, font=_font(10))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=_font(15, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=_font(9))
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=_font(9))
        style.configure("Accent.TButton", font=_font(10, "bold"))
        style.configure("Flat.TButton", font=_font(10))

        # ---- 头部 ----
        head = ttk.Frame(self, style="App.TFrame", padding=(20, 16, 20, 6))
        head.pack(fill="x")
        ttk.Label(head, text="音乐解锁", style="Title.TLabel").pack(anchor="w")
        ttk.Label(head, text="加密音乐格式 → 普通音频，拖拽即可开始",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        # ---- 工具栏 ----
        bar = ttk.Frame(self, style="App.TFrame", padding=(20, 8))
        bar.pack(fill="x")
        self.run_btn = ttk.Button(bar, text="开始转换", style="Accent.TButton",
                                  bootstyle=PRIMARY, command=self.start)
        self.run_btn.pack(side="left")
        ttk.Button(bar, text="添加文件", bootstyle=(SECONDARY, OUTLINE),
                   command=self.add_files).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text="添加文件夹", bootstyle=(SECONDARY, OUTLINE),
                   command=self.add_dir).pack(side="left", padx=6)
        ttk.Button(bar, text="添加Apple链接", bootstyle=(SECONDARY, OUTLINE),
                   command=self.add_apple_urls_dialog).pack(side="left", padx=6)
        ttk.Button(bar, text="清空", bootstyle=(SECONDARY, OUTLINE),
                   command=self.clear).pack(side="left", padx=6)

        bar2 = ttk.Frame(self, style="App.TFrame", padding=(20, 0, 20, 8))
        bar2.pack(fill="x")
        ttk.Button(bar2, text="导入QQ登录态", bootstyle=(SECONDARY, OUTLINE),
                   command=self.import_qq).pack(side="left")
        ttk.Button(bar2, text="检查Apple解密链", bootstyle=(SECONDARY, OUTLINE),
                   command=self.apple_prepare).pack(side="left", padx=6)

        # ---- 文件列表（卡片） ----
        card = ttk.Frame(self, style="Card.TFrame", padding=1)
        card.pack(fill="both", expand=True, padx=20, pady=(2, 8))
        self.listbox = tk.Listbox(card, activestyle="none", relief="flat", bd=0,
                                  highlightthickness=0, bg=SURFACE, fg=TEXT,
                                  selectbackground=ACCENT, selectforeground="#FFFFFF",
                                  font=_font(10))
        self.listbox.pack(fill="both", expand=True, padx=6, pady=6)

        # ---- 底部状态栏 ----
        bottom = ttk.Frame(self, style="App.TFrame", padding=(20, 10, 20, 14))
        bottom.pack(fill="x")
        self.open_btn = ttk.Button(bottom, text="打开输出目录", bootstyle=(SECONDARY, OUTLINE),
                                   command=self.open_out, state="disabled")
        self.open_btn.pack(side="right")
        self.status = ttk.Label(bottom, text="拖文件进来，或点按钮添加", style="Status.TLabel")
        self.status.pack(side="left")

        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            for widget in (self, self.listbox):
                TkinterDnD.TkinterDnD(widget).register_drop_target(widget, DND_FILES, self.on_drop)
        except Exception:
            pass

    # ---------- 弹窗（Fluent 风格） ----------
    def _dialog(self, title, segments, buttons):
        top = tk.Toplevel(self)
        top.title(title)
        top.attributes("-topmost", True)
        top.resizable(False, False)
        top.configure(bg=BG)
        body = tk.Frame(top, bg=BG, padx=28)
        body.pack(fill="x", pady=(18, 0))
        ttk.Label(body, text=title, style="Title.TLabel").pack(anchor="w")
        line = tk.Frame(top, bg=BG, padx=28)
        line.pack(pady=(10, 0))
        normal, bold = _font(10), _font(10, "bold")
        for text, w in segments:
            tk.Label(line, text=text, font=bold if w == "bold" else normal,
                     bg=BG, fg=TEXT, wraplength=420, justify="left").pack(side="left")
        btns = ttk.Frame(top, style="App.TFrame", padding=(0, 16, 0, 18))
        btns.pack(fill="x")
        for label, style_name, cmd in buttons:
            ttk.Button(btns, text=label, bootstyle=style_name,
                       command=lambda c=cmd: (top.destroy(), c())).pack(side="left", padx=6)
        top.update_idletasks()
        x = self.winfo_screenwidth() // 2 - top.winfo_width() // 2
        y = self.winfo_screenheight() // 2 - top.winfo_height() // 2
        top.geometry(f"+{x}+{y}")
        top.lift()
        top.focus_force()

    # ---------- 列表操作 ----------
    def add(self, paths):
        have = {it[0] for it in self.items}
        added = 0
        for fp, disp in collect(paths):
            if fp in have:
                continue
            self.items.append([fp, disp, ""])
            self.listbox.insert("end", disp)
            added += 1
        if added and self.need_qq_login():
            if not self._qq_prompted:
                self._qq_prompted = True
                self.qq_detect_prompt()
        else:
            n = len(self.items)
            self.status.config(text=f"共 {n} 个文件待转换" if added else "没识别到加密音乐文件")

    def add_apple_urls(self, urls):
        import apple_music
        have = {it[0] for it in self.items}
        added = 0
        for u in urls:
            u = u.strip()
            if not apple_music.is_apple_url(u) or u in have:
                continue
            disp = "🔗 " + (u if len(u) <= 70 else u[:67] + "…")
            self.items.append([u, disp, ""])
            self.listbox.insert("end", disp)
            added += 1
        if not added:
            self.status.config(text="没识别到 Apple Music 链接")
            return
        state = self.apple_state()
        if state == "ready":
            self.status.config(text=f"共 {len(self.items)} 个任务待处理（Apple 链就绪，直接解密）")
        elif not self._apple_prompted:
            self._apple_prompted = True
            if state == "unprovisioned":
                self.apple_first_run_prompt()
            else:
                self.apple_login_dialog()

    def add_apple_urls_dialog(self):
        top = tk.Toplevel(self)
        top.title("添加 Apple Music 链接")
        top.attributes("-topmost", True)
        top.configure(bg=BG)
        body = tk.Frame(top, bg=BG, padx=24)
        body.pack(fill="both", expand=True, pady=(16, 0))
        ttk.Label(body, text="添加 Apple Music 链接", style="Title.TLabel").pack(anchor="w")
        tk.Label(body, text="歌曲 / 专辑 / 播放列表链接，每行一个：",
                 font=_font(9), bg=BG, fg=MUTED).pack(anchor="w", pady=(6, 4))
        text = tk.Text(body, width=58, height=6, font=_font(9), relief="solid", bd=1)
        text.pack(fill="x")
        btns = ttk.Frame(top, style="App.TFrame", padding=(0, 12, 0, 14))
        btns.pack(fill="x")
        ttk.Button(btns, text="添加", bootstyle=PRIMARY,
                   command=lambda: (top.destroy(),
                                    self.add_apple_urls(text.get("1.0", "end").splitlines()))
                   ).pack(side="left", padx=6)
        ttk.Button(btns, text="取消", bootstyle=SECONDARY,
                   command=top.destroy).pack(side="left")
        top.update_idletasks()
        x = self.winfo_screenwidth() // 2 - top.winfo_width() // 2
        y = self.winfo_screenheight() // 2 - top.winfo_height() // 2
        top.geometry(f"+{x}+{y}")
        top.lift()
        text.focus_set()

    def add_files(self):
        fs = filedialog.askopenfilenames(title="选择加密音乐文件")
        if fs:
            self.add(list(fs))

    def add_dir(self):
        d = filedialog.askdirectory(title="选择包含加密音乐的文件夹")
        if d:
            self.add([d])

    def on_drop(self, event):
        self.add(self.tk.splitlist(event.data))

    def clear(self):
        self.items.clear()
        self.listbox.delete(0, "end")
        self._qq_prompted = False
        self._apple_prompted = False
        self.status.config(text="已清空")

    # ---------- QQ：单级凭据 ----------
    def need_qq_login(self):
        if not any(os.path.splitext(it[0])[1].lower().startswith((".mgg", ".mflac")) for it in self.items):
            return False
        try:
            import qmc_ekey
            uin, authst = qmc_ekey.load_credentials()
            return not (uin and authst)
        except Exception:
            return True

    def qq_detect_prompt(self):
        self._dialog(
            "需要 QQ 登录态",
            [("检测到 ", "normal"), ("QQ 音乐新版加密格式", "bold"), ("，需要先导入 QQ 登录态才能解密。", "normal")],
            [("导入QQ登录态", PRIMARY, self.import_qq), ("稍后再说", SECONDARY, lambda: None)])

    def import_qq(self):
        import qmc_ekey, browser_cookies
        uin, authst = qmc_ekey.import_from_browser()
        if uin:
            _, _, src = browser_cookies.find_qq_credentials()
            failed = sum(1 for it in self.items if it[2].startswith(" ✗"))
            tip = f"已从 {src} 导入 QQ 登录态（uin={uin}）"
            tip += "，再点「开始转换」重试失败项" if failed else "，musicex 直接解"
            self.status.config(text=tip)
        else:
            subprocess.Popen(["xdg-open", "https://y.qq.com"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.login_prompt()

    def login_prompt(self):
        self._dialog(
            "需要登录",
            [("请在", "normal"), ("音乐文件来源方", "bold"), ("官网上登录，以便本程序进行解密。", "normal")],
            [("我已登录，重新导入", PRIMARY, self.import_qq), ("稍后再说", SECONDARY, lambda: None)])

    # ---------- Apple：首次装配 + 三级链 ----------
    def apple_state(self):
        """ready（直接解密）/ no_auth（引擎在，登录态失效）/ unprovisioned（首次，引擎未装配）"""
        import apple_music
        if not apple_music.provisioned():
            return "unprovisioned"
        if not apple_music.is_logged_in():
            return "no_auth"
        return "ready"

    def apple_first_run_prompt(self):
        self._dialog(
            "需要准备特殊解密引擎",
            [("检测到 ", "normal"), ("Apple Music 链接", "bold"),
             ("。苹果的内容有 FairPlay 加密，需要先在本机准备", "normal"),
             ("特殊解密引擎", "bold"),
             ("（仅首次。组件全内置，解密零件安装包也会自动拉取）。", "normal")],
            [("立即准备", PRIMARY, self.apple_provision_flow),
             ("稍后再说", SECONDARY, self.apple_skip)])

    def apple_skip(self):
        """稍后再说 = 跳过 Apple 任务并标记解密失败。"""
        import apple_music
        for i, it in enumerate(self.items):
            if apple_music.is_apple_url(it[0]) and not it[2]:
                self.set_row(i, " ✗ 未准备解密引擎")
        self.status.config(text="已跳过 Apple 任务（之后可点「检查Apple解密链」准备）")

    def apple_provision_flow(self, apk=None):
        """立即准备：全自动装配（含自动拉取安装包）→ 索取 Apple ID → 直接开始解密。
        apk 参数仅在自动拉取失败、用户手动选择过安装包后重试时传入。"""
        top = tk.Toplevel(self)
        top.title("准备特殊解密引擎")
        top.attributes("-topmost", True)
        top.resizable(False, False)
        top.configure(bg=BG)
        body = tk.Frame(top, bg=BG, padx=28)
        body.pack(fill="x", pady=(18, 0))
        ttk.Label(body, text="准备特殊解密引擎", style="Title.TLabel").pack(anchor="w")
        lbl = tk.Label(top, text="开始装配…", font=_font(10), bg=BG, fg=MUTED,
                       anchor="w", wraplength=400, justify="left")
        lbl.pack(fill="x", padx=28, pady=(10, 0))
        bar = ttk.Progressbar(top, mode="indeterminate", bootstyle=PRIMARY)
        bar.pack(fill="x", padx=28, pady=(8, 16))
        bar.start(12)
        top.update_idletasks()
        x = self.winfo_screenwidth() // 2 - top.winfo_width() // 2
        y = self.winfo_screenheight() // 2 - top.winfo_height() // 2
        top.geometry(f"+{x}+{y}")
        top.lift()

        def do():
            import apple_music
            try:
                apple_music.provision(lambda t: top.after(0, lambda: lbl.config(text=t)),
                                      apk_path=apk)
            except Exception as e:
                msg = str(e)
                if msg == "NEED_APK":
                    top.after(0, lambda: (top.destroy(), self._ask_apk_fallback()))
                else:
                    top.after(0, lambda: (top.destroy(), self._provision_fail(msg)))
                return
            top.after(0, lambda: (top.destroy(), self._provision_ok()))

        threading.Thread(target=do, daemon=True).start()

    def _ask_apk_fallback(self):
        """自动拉取安装包失败时的兜底：让用户手动选一个。"""
        apk = filedialog.askopenfilename(
            title="自动拉取失败，请手动选择 Apple Music 安装包（.apkm/.apk，需 3.6.0-beta-1109）",
            filetypes=[("Android 安装包", "*.apkm *.apk")])
        if apk:
            self.apple_provision_flow(apk=apk)
        else:
            self.apple_skip()

    def _provision_ok(self):
        import apple_music
        self._apple_prompted = False
        if apple_music.is_logged_in():
            self._apple_ready_tip()
        else:
            # 索取 Apple ID 并注明用处，登录成功后直接开始解密
            self.apple_login_dialog(on_success=self.start)

    def _provision_fail(self, msg):
        self._dialog(
            "准备失败",
            [("装配特殊解密引擎时出错：", "normal"), (msg[:80], "bold"),
             ("。可重试，或稍后再说。", "normal")],
            [("重试", PRIMARY, self.apple_provision_flow),
             ("稍后再说", SECONDARY, self.apple_skip)])

    def apple_prepare(self):
        """手动走查三级链（工具栏入口）：能静默过的不打扰，卡在哪级弹哪级。"""
        self.status.config(text="正在走查 Apple 解密链（环境 → 引擎 → 登录态）…")

        def do():
            import apple_music
            if not apple_music.provisioned():
                self.after(0, self.apple_first_run_prompt)
                return
            ok, stage, detail = apple_music.check_chain()
            self.after(0, lambda: self._apple_stage(ok, stage, detail))

        threading.Thread(target=do, daemon=True).start()

    def _apple_stage(self, ok, stage, detail):
        if ok:
            self._apple_ready_tip()
            return
        if stage == "auth":
            self.apple_login_dialog()
            return
        self._dialog(
            "Apple 解密环境未就绪",
            [("走查卡在", "normal"), (detail, "bold"),
             ("。可先确认 Docker 服务与 wrapper-v2 容器状态。", "normal")],
            [("重试", PRIMARY, self.apple_prepare), ("稍后再说", SECONDARY, lambda: None)])

    def _apple_ready_tip(self):
        failed = sum(1 for it in self.items if it[2].startswith(" ✗"))
        tip = "Apple 解密链就绪，链接直接下"
        tip += "，再点「开始转换」重试失败项" if failed else ""
        self.status.config(text=tip)

    def apple_login_dialog(self, on_success=None):
        top = tk.Toplevel(self)
        top.title("登录 Apple ID")
        top.attributes("-topmost", True)
        top.resizable(False, False)
        top.configure(bg=BG)
        body = tk.Frame(top, bg=BG, padx=28)
        body.pack(fill="x", pady=(18, 0))
        ttk.Label(body, text="登录 Apple ID", style="Title.TLabel").pack(anchor="w")
        hint = tk.Frame(top, bg=BG, padx=28)
        hint.pack(pady=(8, 0))
        tk.Label(hint, text="请登录", font=_font(10), bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hint, text="音乐文件来源方", font=_font(10, "bold"), bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hint, text="账号（需订阅 Apple Music）。", font=_font(10),
                 bg=BG, fg=TEXT).pack(side="left")
        note = tk.Frame(top, bg=BG, padx=28)
        note.pack(pady=(2, 0))
        tk.Label(note, text="仅用于调用其解密服务，凭据缓存在本机，不会上传他处。",
                 font=_font(10, "bold"), bg=BG, fg="#C42B1C",
                 wraplength=380, justify="left").pack(side="left")

        form = tk.Frame(top, bg=BG, padx=28)
        form.pack(fill="x", pady=(14, 0))
        entries = {}
        for row, (label, show) in enumerate((("Apple ID（邮箱或手机号）", None),
                                             ("密码", "*"),
                                             ("验证码（如收到双重认证才填）", None))):
            tk.Label(form, text=label, font=_font(9), bg=BG, fg=MUTED,
                     anchor="w").grid(row=row * 2, column=0, sticky="w", pady=(6, 0))
            e = tk.Entry(form, width=36, font=_font(10), relief="solid", bd=1, show=show or "")
            e.grid(row=row * 2 + 1, column=0, sticky="w")
            entries[label] = e
        err = tk.Label(form, text="", font=_font(9), bg=BG, fg="#C42B1C", anchor="w")
        err.grid(row=6, column=0, sticky="w", pady=(8, 0))

        btns = ttk.Frame(top, style="App.TFrame", padding=(0, 16, 0, 18))
        btns.pack(fill="x", pady=(14, 0))
        login_btn = ttk.Button(btns, text="登录", bootstyle=PRIMARY)
        login_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="稍后再说", bootstyle=SECONDARY,
                   command=top.destroy).pack(side="left")

        def submit():
            import apple_music
            apple_id = entries["Apple ID（邮箱或手机号）"].get().strip()
            password = entries["密码"].get()
            code = entries["验证码（如收到双重认证才填）"].get().strip() or None
            if not apple_id or not password:
                err.config(text="Apple ID 和密码都得填")
                return
            login_btn.config(state="disabled")
            err.config(text="正在登录…", fg=MUTED)

            def do():
                try:
                    apple_music.login(apple_id, password, code)
                except apple_music.WrapperError as e:
                    msg = str(e)
                    top.after(0, lambda: (err.config(text=msg[:60], fg="#C42B1C"),
                                          login_btn.config(state="normal")))
                    return

                def ok():
                    top.destroy()
                    if on_success:
                        on_success()
                    else:
                        self._apple_ready_tip()

                top.after(0, ok)

            threading.Thread(target=do, daemon=True).start()

        login_btn.config(command=submit)
        entries["Apple ID（邮箱或手机号）"].focus_set()
        top.bind("<Return>", lambda _e: submit())
        top.update_idletasks()
        x = self.winfo_screenwidth() // 2 - top.winfo_width() // 2
        y = self.winfo_screenheight() // 2 - top.winfo_height() // 2
        top.geometry(f"+{x}+{y}")
        top.lift()

    # ---------- 转换 ----------
    def start(self):
        if not self.items:
            self.status.config(text="先添加文件或链接")
            return
        self.run_btn.config(state="disabled")
        self.open_btn.config(state="disabled")
        threading.Thread(target=self.work, daemon=True).start()

    def set_row(self, i, suffix):
        it = self.items[i]
        it[2] = suffix
        self.listbox.after(0, lambda: (self.listbox.delete(i),
                                       self.listbox.insert(i, f"{it[1]} {suffix}"),
                                       self.listbox.see(i)))

    def set_status(self, text):
        self.status.after(0, lambda: self.status.config(text=text))

    def work(self):
        ok, fail = 0, 0
        n = len(self.items)
        for i, (path, _disp, _st) in enumerate(self.items, 1):
            self.set_status(f"[{i}/{n}] {os.path.basename(path)}")
            good, why = self.unlock(path)
            if good:
                ok += 1
                self.set_row(i - 1, " ✓")
            else:
                fail += 1
                self.set_row(i - 1, f" ✗ {why[:50]}")
        self.set_status(f"完成：成功 {ok}，失败 {fail}" + (f"（输出在「{OUT_NAME}」）" if ok else ""))
        if ok and self.outdir:
            self.open_btn.after(0, lambda: self.open_btn.config(state="normal"))
        self.run_btn.after(0, lambda: self.run_btn.config(state="normal"))

    def unlock(self, path):
        import apple_music
        if apple_music.is_apple_url(path):
            self.outdir = os.path.join(os.path.expanduser("~/Music"), OUT_NAME)
            if not apple_music.is_logged_in():
                return False, "解密链未就绪（点「检查Apple解密链」）"
            return apple_music.download(path, self.outdir, progress_cb=self.set_status)
        self.outdir = os.path.join(os.path.dirname(path) or ".", OUT_NAME)
        r = subprocess.run([UM, "-i", path, "-o", self.outdir, "--overwrite"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return True, ""
        ext = os.path.splitext(path)[1].lower()
        if ext.startswith((".mgg", ".mflac")):
            return self.unlock_qmc2(path)
        why = (r.stderr or r.stdout).strip().splitlines()
        return False, (why[-1] if why else "未知错误")

    def unlock_qmc2(self, path):
        import qmc_ekey
        info = qmc_ekey.parse_musicex_footer(path)
        if not info:
            return False, "非 musicex 格式"
        _, media_mid, filename = info
        ekey = qmc_ekey.fetch_ekey(media_mid, filename)
        if not ekey:
            return False, "无 QQ 登录态（点「导入QQ登录态」）"
        r = subprocess.run([QMC, "--ekey", ekey, path, self.outdir],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return True, ""
        why = (r.stderr or r.stdout).strip().splitlines()
        return False, (why[-1] if why else "解密失败")

    def open_out(self):
        if self.outdir:
            subprocess.Popen(["xdg-open", self.outdir],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()  # 冻结模式下 gamdl 以子进程跑模块，需要这个
    import apple_music
    apple_music.seed_assets()  # 首跑：bundle 内置资产落到运行时目录
    if "--self-test" in sys.argv:  # 打包自检：资产、引擎、冻结子进程、苹果链
        print("镜像包:", os.path.exists(apple_music.IMAGE_TAR))
        print("零件哈希表:", len(apple_music._expected_libs()))
        print("引擎 um:", os.path.exists(UM), "| qmc-decoder:", os.path.exists(QMC))
        rc, tail = apple_music._module_run("gamdl", ["--version"])
        print("gamdl 子进程 rc =", rc, "|", tail[-1] if tail else "")
        print("苹果链:", apple_music.check_chain())
        sys.exit(0)
    for m, name in ((UM, "um"), (QMC, "qmc-decoder")):
        if not os.path.exists(m):
            sys.exit(f"缺少解密引擎 {m}")
    App().mainloop()
