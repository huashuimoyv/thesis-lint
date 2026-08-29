"""图形界面：双击 exe 或拖文件到图标时使用（Windows）。

深色「夜间自习室」风格，与网页版同一设计语言；v0.4.0 起与网页功能对齐：
拖拽进件、体检报告、一键生成修正后列表、复制/导出。

测试钩子（环境变量）：
- THESISLINT_GUI_AUTOCLOSE_MS  窗口 N 毫秒后自动关闭
- THESISLINT_GUI_AUTODEMO=1    启动后自动用示例论文跑一次体检
- THESISLINT_GUI_AUTOFIX=1     体检完成后自动生成修正列表
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from pathlib import Path

# ---- 配色（与网页版同一「夜间自习室」体系）----
BG = "#0b0e13"
SURFACE = "#0f141b"
RAISE = "#131a23"
LINE = "#1e2630"
LINE_HI = "#31405a"
TEXT = "#e6edf3"
MUTED = "#8b949e"
FAINT = "#56606b"
ACCENT = "#5b9bff"
ACCENT_HI = "#8ab8ff"
OK = "#7ee787"
WARN = "#e3b341"
ERR = "#ff7b72"


def _supports_tk() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:  # ImportError 或显示环境缺失  # noqa: BLE001  刻意宽捕获：任一失败都走降级路径
        return False


def _launched_from_explorer() -> bool:
    """是否由资源管理器启动（拖文件到图标 / 双击）。

    借助 kernel32.GetConsoleProcessList：用户手动开的控制台里还有 shell
    等其他进程；而资源管理器给控制台程序拉起的临时控制台里只有自己。
    没有控制台（Git Bash 管道/脚本调用）不可能是拖拽，必须视为命令行。
    """
    if os.name != "nt":
        return False
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        if not k32.GetConsoleWindow():
            return False
        buf = (ctypes.c_uint32 * 1)()
        return k32.GetConsoleProcessList(buf, 1) == 1
    except Exception:  # noqa: BLE001  刻意宽捕获：任一失败都走降级路径
        return False


def should_launch_gui(argv: list[str]) -> bool:
    """双模式分发决策。argv 永远是显式列表，不含本程序名。"""
    if not _supports_tk():
        return False
    if len(argv) == 0:
        return True  # 直接双击 exe
    if (
        len(argv) == 1
        and argv[0].lower().endswith(".docx")
        and not argv[0].startswith("-")
    ):
        return _launched_from_explorer()
    return False


_DEMO_ENTRIES = [
    "[1] 刘知远. 大模型时代的自然语言处理[M]. 北京: 清华大学出版社, 2023: 15-20.",
    "[2] Vaswani A, Shazeer N, Parmar J, et al. Attention is all you need[C]//NeurIPS. 2017: 5998-6008.",
    "[3] 张三，李四. 一种深度学习方法[J]. 计算机学报，2024，47（3）：100-110",
    "[4] Brown T B, Mann B, Ryder N, Subbiah M, Kaplan J. Language models are few-shot learners[J]. NeurIPS, 2020.",
    "[5] 中国互联网络信息中心. 第53次中国互联网络发展状况统计报告[R/OL]. (2024-03-22)[2025-01-10]. https://www.cnnic.net.cn/report.html.",
]


class App:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter import font as tkfont

        self._tk = tk
        self._filedialog = filedialog
        self._messagebox = messagebox

        root = self._make_root(tk)
        self.root = root
        root.title("thesis-lint · 参考文献国标体检")
        root.geometry("940x700")
        root.minsize(780, 580)
        root.configure(bg=BG)

        families = set(tkfont.families())
        self._ui = "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else "Microsoft YaHei"
        self._mono = "Cascadia Code" if "Cascadia Code" in families else "Consolas"

        self._style_ttk(ttk)
        self._build_header()
        self._build_drop_zone()
        self._build_status()
        self._build_toolbar()
        self._build_report_view()
        self._build_fix_panel()

        self._md_cache: str | None = None
        self._text_cache = ""
        self._fix_cache = ""
        self._last_path: str | None = None
        self._hero_mode = "idle"   # idle / done
        self._pulse_step = False
        self._pulse()

        # 测试钩子
        self._auto_fix_pending = os.environ.get("THESISLINT_GUI_AUTOFIX") == "1"
        if os.environ.get("THESISLINT_GUI_AUTODEMO") == "1":
            root.after(300, self._auto_demo)
        auto_close = os.environ.get("THESISLINT_GUI_AUTOCLOSE_MS")
        if auto_close and auto_close.isdigit():
            root.after(int(auto_close), root.destroy)

    # ---------- 窗口与主题 ----------

    def _make_root(self, tk):
        """优先 tkinterdnd2 的 Tk 获得整窗拖拽；失败退回普通 Tk。"""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnTk  # type: ignore

            root = TkinterDnTk()
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", self._on_drop)
            return root
        except Exception:  # noqa: BLE001  tkinterdnd2 不可用时回退纯 Tk（拖拽降级为点击）
            return tk.Tk()

    def _style_ttk(self, ttk):
        style = ttk.Style(self.root)
        # 刻意宽捕获：主题不可用就用默认主题
        with contextlib.suppress(Exception):
            style.theme_use("clam")
        style.configure("TScrollbar", background=RAISE, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, lightcolor=RAISE,
                        darkcolor=RAISE)
        style.map("TScrollbar", background=[("active", LINE_HI)])

    def _hover(self, btn, normal, hovered):
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hovered))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=normal))

    def _button(self, parent, text, command, *, kind="ghost"):
        tk = self._tk
        styles = {
            "accent": (ACCENT, "#0b0e13", ACCENT_HI, "#0b0e13"),
            "ghost":  (RAISE, TEXT, LINE_HI, TEXT),
            "warn":   (RAISE, WARN, LINE_HI, WARN),
            "ok":     ("#1a3f2a", OK, "#215237", OK),
        }
        bg, fg, hbg, hfg = styles[kind]
        btn = tk.Button(
            parent, text=text, command=command,
            font=(self._ui, 9), cursor="hand2",
            relief="flat", bd=0, padx=14, pady=5,
            bg=bg, fg=fg, activebackground=hbg, activeforeground=hfg,
            disabledforeground=FAINT, state="normal",
        )
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hbg) if str(btn["state"]) == "normal" else None)
        btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
        return btn

    def _set_enabled(self, btn, enabled):
        btn.configure(state="normal" if enabled else "disabled")

    # ---------- 区块构建 ----------

    def _build_header(self):
        tk = self._tk
        from . import __version__
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=26, pady=(18, 8))
        tk.Label(head, text="thesis", font=(self._ui, 12, "bold"), bg=BG, fg=TEXT).pack(side="left")
        tk.Label(head, text="·", font=(self._ui, 12, "bold"), bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(head, text="lint", font=(self._ui, 12, "bold"), bg=BG, fg=TEXT).pack(side="left")
        tk.Label(head, text=f"  参考文献是否符合 GB/T 7714-2025 · v{__version__}",
                 font=(self._ui, 9), bg=BG, fg=MUTED).pack(side="left", padx=(10, 0))
        tk.Label(head, text="本地解析 · 不上传", font=(self._ui, 8), bg=BG, fg=FAINT).pack(side="right")

    def _build_drop_zone(self):
        tk = self._tk
        self.drop = tk.Frame(
            self.root, bg=SURFACE,
            highlightthickness=1, highlightbackground=LINE, highlightcolor=LINE,
        )
        self.drop.pack(fill="x", padx=26, pady=(6, 4))

        # 海报态
        self.hero = tk.Frame(self.drop, bg=SURFACE)
        self.hero.pack(pady=34)
        tk.Label(self.hero, text="把论文拖进来，即刻体检",
                 font=(self._ui, 16, "bold"), bg=SURFACE, fg=TEXT).pack()
        tk.Label(self.hero,
                 text="拖入窗口、拖到 exe 图标、或点击选择 · 只支持 .docx（.doc 请先另存为 .docx）",
                 font=(self._ui, 9), bg=SURFACE, fg=MUTED).pack(pady=(8, 16))
        row = tk.Frame(self.hero, bg=SURFACE)
        row.pack()
        self.btn_pick = self._button(row, "选择文件", self.pick_file, kind="accent")
        self.btn_pick.pack(side="left", padx=5)
        self.btn_demo = self._button(row, "用示例论文试一试", self.check_demo, kind="ghost")
        self.btn_demo.pack(side="left", padx=5)

        # 完成态（收拢成细条）
        self.done = tk.Frame(self.drop, bg=SURFACE)
        self.done_name = tk.Label(self.done, text="", font=(self._mono, 10),
                                  bg=SURFACE, fg=OK)
        self.done_name.pack(side="left")
        tk.Label(self.done, text="  点击或拖入新文件，重新体检",
                 font=(self._ui, 9), bg=SURFACE, fg=ACCENT).pack(side="left")

        for w in (self.drop, self.hero, self.done):
            w.bind("<Button-1>", lambda _e: self.pick_file())
        for child in self.hero.winfo_children():
            child.bind("<Button-1>", lambda _e: self.pick_file())

    def _build_status(self):
        tk = self._tk
        self.status = tk.Label(self.root, text="等待文件…", font=(self._ui, 9),
                               bg=BG, fg=MUTED, anchor="w")
        self.status.pack(fill="x", padx=28, pady=(6, 2))

    def _build_toolbar(self):
        bar = self._tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=26, pady=(6, 8))
        self.btn_copy = self._button(bar, "复制报告", self.copy_report, kind="ghost")
        self.btn_md = self._button(bar, "导出 Markdown", self.export_md, kind="ghost")
        self.btn_fix = self._button(bar, "生成修正后列表", self.generate_fix, kind="warn")
        for b in (self.btn_copy, self.btn_md, self.btn_fix):
            b.pack(side="left", padx=(0, 8))
            self._set_enabled(b, False)

    def _make_code_view(self, parent, height):
        tk = self._tk
        frame = tk.Frame(parent, bg=LINE)
        text = tk.Text(
            frame, height=height, wrap="word",
            bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            selectbackground="#2d4a73", selectforeground=TEXT,
            relief="flat", bd=0, highlightthickness=1, highlightbackground=LINE,
            font=(self._mono, 10), padx=16, pady=12, state="disabled",
        )
        text.pack(side="left", fill="both", expand=True)
        from tkinter import ttk
        sb = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        sb.pack(side="right", fill="y")
        text.configure(yscrollcommand=sb.set)
        text.tag_configure("err", foreground=ERR, font=(self._mono, 10, "bold"))
        text.tag_configure("warn", foreground=WARN, font=(self._mono, 10, "bold"))
        text.tag_configure("head", foreground=OK)
        text.tag_configure("note", foreground=WARN)
        return frame, text

    def _build_report_view(self):
        frame, text = self._make_code_view(self.root, 12)
        self.report_box, self.report = frame, text
        frame.pack(fill="both", expand=True, padx=26, pady=(0, 4))

    def _build_fix_panel(self):
        tk = self._tk
        self.fix_panel = tk.Frame(self.root, bg=BG)
        head = tk.Frame(self.fix_panel, bg=BG)
        head.pack(fill="x", pady=(10, 6))
        tk.Label(head, text="修正后的参考文献", font=(self._ui, 11, "bold"),
                 bg=BG, fg=OK).pack(side="left")
        self.fix_stats = tk.Label(head, text="", font=(self._ui, 9),
                                  bg=BG, fg=MUTED)
        self.fix_stats.pack(side="left", padx=(12, 0))

        frame, text = self._make_code_view(self.fix_panel, 9)
        self.fix_box, self.fix_text = frame, text
        frame.pack(fill="both", expand=True)

        row = tk.Frame(self.fix_panel, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text="⚠︎ 重新编号后请同步修改正文引用编号；粘贴回 Word 后建议再人工过一遍",
                 font=(self._ui, 8), bg=BG, fg=FAINT).pack(side="left")
        self.btn_fix_copy = self._button(row, "复制修正后条目", self.copy_fix, kind="ok")
        self.btn_fix_copy.pack(side="right")
        self.btn_fix_txt = self._button(row, "导出 txt", self.export_fix_txt, kind="ghost")
        self.btn_fix_txt.pack(side="right", padx=(0, 8))

    # ---------- 动效 ----------

    def _pulse(self):
        """拖拽区边框呼吸（海报态时）。"""
        try:
            if self._hero_mode == "idle":
                self._pulse_step = not self._pulse_step
                self.drop.configure(highlightbackground=LINE_HI if self._pulse_step else LINE)
            self.root.after(700, self._pulse)
        except self._tk.TclError:
            pass  # 窗口已关闭

    # ---------- 进件 ----------

    def pick_file(self):
        path = self._filedialog.askopenfilename(
            title="选择论文", filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            self.check(path)

    def _on_drop(self, event):
        data = event.data.strip()
        if data.startswith("{") and data.endswith("}"):
            data = data[1:-1]
        if data.lower().endswith(".docx"):
            self.check(data)
        else:
            self._messagebox.showwarning(
                "不支持的文件", "目前只支持 .docx 文件。\n如果是 .doc，请先用 Word 另存为 .docx。")

    def check_demo(self):
        import tempfile
        try:
            from docx import Document
        except Exception as exc:  # pragma: no cover  # noqa: BLE001  刻意宽捕获：任一失败都走降级路径
            self._set_status(f"无法生成示例：{exc}", ERR)
            return
        path = str(Path(tempfile.gettempdir()) / "thesislint_demo.docx")
        doc = Document()
        doc.add_heading("参考文献", level=1)
        for e in _DEMO_ENTRIES:
            doc.add_paragraph(e)
        doc.save(path)
        self.check(path, display_name="示例论文")

    def _auto_demo(self):
        self.check_demo()

    # ---------- 分析 ----------

    def check(self, path: str, display_name: str | None = None):
        self._last_path = path
        self._display_name = display_name or Path(path).name
        self._hero_mode = "idle"
        self._set_status(f"正在检查 {self._display_name} …", ACCENT)
        self.drop.configure(highlightbackground=LINE, highlightcolor=LINE)
        for b in (self.btn_copy, self.btn_md, self.btn_fix):
            self._set_enabled(b, False)
        self.fix_panel.pack_forget()
        self._set_enabled(self.btn_fix_copy, False)
        self._set_enabled(self.btn_fix_txt, False)
        threading.Thread(target=self._work, args=(path, self._display_name), daemon=True).start()

    def _work(self, path: str, display_name: str):
        try:
            from .cli import analyze
            from .report import build_markdown_report, build_text_report

            report = analyze(Path(path))
            text = build_text_report(report)
            md = build_markdown_report(report)
            summary = f"完成：{report.error_count} 个错误，{report.warn_count} 个警告"
            color = ERR if report.error_count else (WARN if report.warn_count else OK)
            found = report.found_section
            stats = {"total": len(report.entries), "errors": report.error_count,
                     "warns": report.warn_count}
            self.root.after(0, lambda: self._finish(
                path, display_name, text, md, summary, color, found, stats))
        except Exception as exc:  # 解析失败等  # noqa: BLE001  刻意宽捕获：任一失败都走降级路径
            detail = str(exc) or exc.__class__.__name__
            self.root.after(0, lambda: self._finish_error(detail))

    def _finish(self, path, display_name, text, md, summary, color, found, stats):
        if self._last_path != path:
            return
        self._text_cache = text
        self._md_cache = md

        # 拖拽区收拢为细条
        self._hero_mode = "done"
        self.hero.pack_forget()
        self.done_name.configure(text=f"✓ {display_name}  {stats['total']} 条参考文献")
        self.done.pack(pady=13, padx=20, fill="x")

        self._set_status(summary, color)
        # 报告（带色渲染）
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        for line in text.splitlines(True):
            if "[ERROR]" in line:
                tags = ("err",)
            elif "[WARN ]" in line or "[WARN]" in line:
                tags = ("warn",)
            elif line.startswith("体检结果"):
                tags = ("head",)
            else:
                tags = ()
            self.report.insert("end", line, tags)
        self.report.configure(state="disabled")

        if found and stats["total"] > 0:
            self._set_enabled(self.btn_fix, True)
        self._set_enabled(self.btn_copy, True)
        self._set_enabled(self.btn_md, True)

        if self._auto_fix_pending:
            self._auto_fix_pending = False
            self.root.after(200, self.generate_fix)

    def _finish_error(self, detail: str):
        self._set_status(f"检查失败：{detail}", ERR)

    def _set_status(self, msg: str, color: str):
        self.status.configure(text=msg, fg=color)

    # ---------- 修正列表 ----------

    def generate_fix(self):
        if not self._last_path:
            return
        self._set_enabled(self.btn_fix, False)
        self._set_status("正在生成修正后列表 …", ACCENT)
        path = self._last_path
        threading.Thread(target=self._fix_work, args=(path,), daemon=True).start()

    def _fix_work(self, path: str):
        try:
            from .cli import analyze
            from .fixer import fix_entries

            report = analyze(Path(path))
            result = fix_entries([e.text for e in report.entries])
            lines = result["lines"]
            s = result["summary"]
            header = (f"共 {s['total']} 条 · 自动修正 {s['auto_fixed']} 条 · "
                      f"{s['manual_needed']} 条需人工处理"
                      + (" · 已重新编号" if s["renumbered"] else ""))
            manual_lines = []
            for e in result["results"]:
                if e.unresolved:
                    manual_lines.append(
                        f"· 第 {e.index} 条（{e.original[:40]}…）：{'；'.join(e.unresolved)}")
            body = "\n".join(lines)
            fix_display = header + "\n\n" + body
            if manual_lines:
                fix_display += "\n\n以下条目无法全自动修正，请人工处理：\n" + "\n".join(manual_lines)
            self.root.after(0, lambda: self._finish_fix(fix_display, header, body,
                                                        len(manual_lines)))
        except Exception as exc:  # noqa: BLE001  刻意宽捕获：任一失败都走降级路径
            detail = str(exc) or exc.__class__.__name__
            self.root.after(0, lambda: self._set_status(f"生成失败：{detail}", ERR))
            self.root.after(0, lambda: self._set_enabled(self.btn_fix, True))

    def _finish_fix(self, fix_display: str, header: str, body: str, n_manual: int):
        self._fix_cache = body
        self.fix_stats.configure(text=header)
        self.fix_text.configure(state="normal")
        self.fix_text.delete("1.0", "end")
        for line in fix_display.splitlines(True):
            if line.startswith("共 "):
                tags = ("head",)
            elif line.startswith("· 第 "):
                tags = ("note",)
            else:
                tags = ()
            self.fix_text.insert("end", line, tags)
        self.fix_text.configure(state="disabled")
        self.fix_panel.pack(fill="both", expand=True, padx=26, pady=(0, 6))
        self._set_enabled(self.btn_fix_copy, True)
        self._set_enabled(self.btn_fix_txt, True)
        self._set_status("修正后列表已生成，可一键复制", OK if n_manual == 0 else WARN)

    # ---------- 导出 ----------

    def copy_report(self):
        content = self._text_cache
        if not content:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self._set_status("报告已复制到剪贴板", OK)

    def copy_fix(self):
        if not self._fix_cache:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._fix_cache)
        self._set_status("修正后列表已复制，去 Word 里粘贴吧", OK)

    def export_md(self):
        if not self._md_cache:
            return
        target = self._filedialog.asksaveasfilename(
            title="导出体检报告", defaultextension=".md",
            initialfile="参考文献体检报告.md", filetypes=[("Markdown", "*.md")],
        )
        if not target:
            return
        Path(target).write_text(self._md_cache, encoding="utf-8")
        self._set_status(f"已导出：{target}", OK)

    def export_fix_txt(self):
        if not self._fix_cache:
            return
        target = self._filedialog.asksaveasfilename(
            title="导出修正后列表", defaultextension=".txt",
            initialfile="参考文献_修正后.txt", filetypes=[("文本文件", "*.txt")],
        )
        if not target:
            return
        Path(target).write_text(self._fix_cache, encoding="utf-8")
        self._set_status(f"已导出：{target}", OK)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def run_gui() -> int:
    """入口：返回进程退出码。"""
    if not _supports_tk():
        print("当前环境缺少图形界面支持（tkinter），请改用命令行方式：thesislint 论文.docx",
              file=sys.stderr)
        return 2
    if os.name == "nt":
        # 刻意宽捕获：DPI 感知失败不影响功能
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    try:
        app = App()
    except Exception as exc:  # noqa: BLE001  刻意宽捕获：任一失败都走降级路径
        print(f"无法打开图形界面：{exc}\n可改用命令行：thesislint 论文.docx", file=sys.stderr)
        return 2
    return app.run()
