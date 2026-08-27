"""图形界面：双击 exe 或无参数启动时使用。

支持三种进件方式：拖拽 docx 到窗口（需 tkinterdnd2）、点击选择文件、
以及从资源管理器把文件拖到 exe 图标上（由 cli 分发进来）。
分析在后台线程执行，避免大文档冻结窗口。

测试钩子：设置环境变量 THESISLINT_GUI_AUTOCLOSE_MS 可让窗口 N 毫秒后自动关闭。
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path


def _supports_tk() -> bool:
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:  # ImportError 或显示环境缺失
        return False


def _launched_from_explorer() -> bool:
    """是否由资源管理器启动（拖文件到图标 / 双击）。

    借助 kernel32.GetConsoleProcessList：用户手动开的控制台里还有 shell
    等其他进程；而资源管理器给控制台程序拉起的临时控制台里只有自己。
    注意：没有控制台（如 Git Bash 管道/脚本调用）不可能是拖拽——
    Windows 会给拖拽启动的临时控制台——因此必须视为命令行。
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
    except Exception:
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
        # 拖 docx 到 exe 图标：走图形界面，避免黑窗一闪而过
        return _launched_from_explorer()
    return False


class App:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import filedialog, font, messagebox, scrolledtext, ttk

        self._tk = tk
        self._messagebox = messagebox
        self._filedialog = filedialog

        root = self._make_root(tk)
        self.root = root
        self._md_cache: str | None = None
        self._last_path: str | None = None

        ui_font = font.nametofont("TkDefaultFont").copy()
        ui_font.configure(size=10)
        root.option_add("*Font", ui_font)

        ttk.Label(
            root, text="毕业论文「国标体检」· 参考文献是否符合 GB/T 7714-2025",
            padding=(12, 10),
        ).pack()

        # 拖放/选择区域
        self.drop_zone = tk.Label(
            root,
            text="将论文 .docx 拖到这里\n或点击选择文件"
            + ("" if getattr(self, "_dnd_ok", False) else "\n（此版本未启用拖拽，请点击选择）"),
            bg="#eef4fb", fg="#1f6feb",
            width=52, height=7, cursor="hand2",
            highlightthickness=2, highlightbackground="#a5c8f0",
        )
        self.drop_zone.pack(padx=16, pady=(2, 8))
        self.drop_zone.bind("<Button-1>", lambda _e: self.pick_file())

        self.status = ttk.Label(root, text="等待文件…", foreground="#666666")
        self.status.pack(pady=(0, 4))

        self.result = scrolledtext.ScrolledText(root, width=84, height=20, state="disabled")
        self.result.pack(padx=16, pady=4)

        btns = ttk.Frame(root, padding=(0, 8))
        btns.pack()
        self.btn_copy = ttk.Button(btns, text="复制报告", command=self.copy_report, state="disabled")
        self.btn_copy.pack(side="left", padx=6)
        self.btn_export = ttk.Button(btns, text="导出 Markdown", command=self.export_md, state="disabled")
        self.btn_export.pack(side="left", padx=6)

        # 测试钩子：自动关闭
        auto_close = os.environ.get("THESISLINT_GUI_AUTOCLOSE_MS")
        if auto_close and auto_close.isdigit():
            root.after(int(auto_close), root.destroy)

    def _make_root(self, tk):  # noqa: ANN001
        """优先用 tkinterdnd2 的 Tk 以获得拖拽能力，失败则退回普通 Tk。"""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnTk  # type: ignore

            root = TkinterDnTk()
            self._dnd_ok = True
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", self._on_drop_dnd)
            return root
        except Exception:
            root = tk.Tk()
            self._dnd_ok = False
            return root

    # ---------- 进件 ----------

    def pick_file(self) -> None:
        path = self._filedialog.askopenfilename(
            title="选择论文", filetypes=[("Word 文档", "*.docx"), ("所有文件", "*.*")]
        )
        if path:
            self.check(path)

    def _on_drop_dnd(self, event) -> None:  # noqa: ANN001
        # 带空格的路径会被花括号包裹：{C:\dir with space\a.docx}
        data = event.data.strip()
        if data.startswith("{") and data.endswith("}"):
            data = data[1:-1]
        if data.lower().endswith(".docx"):
            self.check(data)
        else:
            self._messagebox.showwarning("不支持的文件", "目前只支持 .docx 文件。\n"
                                          "如果是 .doc，请先用 Word 另存为 .docx。")

    # ---------- 分析 ----------

    def check(self, path: str) -> None:
        self._last_path = path
        self.status.configure(text=f"正在检查 {Path(path).name} …", foreground="#1f6feb")
        self.btn_copy.configure(state="disabled")
        self.btn_export.configure(state="disabled")
        threading.Thread(target=self._work, args=(path,), daemon=True).start()

    def _work(self, path: str) -> None:
        try:
            from .cli import analyze
            from .report import build_markdown_report, build_text_report

            report = analyze(Path(path))
            text = build_text_report(report)
            md = build_markdown_report(report)
            summary = f"完成：{report.error_count} 个错误，{report.warn_count} 个警告"
            color = "#c62828" if report.error_count else ("#b58a00" if report.warn_count else "#1a7f37")
            self.root.after(0, lambda: self._finish(path, text, md, summary, color))
        except Exception as exc:  # 解析失败等
            detail = f"{exc}" or exc.__class__.__name__
            self.root.after(0, lambda: self._finish_error(detail))

    def _finish(self, path: str, text: str, md: str, summary: str, color: str) -> None:
        if not self._same_file(path):
            return
        self._md_cache = md
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("1.0", text)
        self.result.configure(state="disabled")
        self.status.configure(text=summary, foreground=color)
        self.btn_copy.configure(state="normal")
        self.btn_export.configure(state="normal")

    def _finish_error(self, detail: str) -> None:
        self.status.configure(text=f"检查失败：{detail}", foreground="#c62828")

    def _same_file(self, path: str) -> bool:
        return path == self._last_path

    # ---------- 导出 ----------

    def copy_report(self) -> None:
        content = self.result.get("1.0", "end").strip()
        if not content:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status.configure(text="已复制到剪贴板", foreground="#1a7f37")

    def export_md(self) -> None:
        if not self._md_cache:
            return
        target = self._filedialog.asksaveasfilename(
            title="导出体检报告",
            defaultextension=".md",
            initialfile="参考文献体检报告.md",
            filetypes=[("Markdown", "*.md")],
        )
        if not target:
            return
        Path(target).write_text(self._md_cache, encoding="utf-8")
        self.status.configure(text=f"已导出：{target}", foreground="#1a7f37")

    def run(self) -> int:
        self.root.mainloop()
        return 0


def run_gui() -> int:
    """入口：返回进程退出码。"""
    if not _supports_tk():
        print("当前环境缺少图形界面支持（tkinter），请改用命令行方式：thesislint 论文.docx", file=sys.stderr)
        return 2
    try:
        app = App()
    except Exception as exc:
        print(f"无法打开图形界面：{exc}\n可改用命令行：thesislint 论文.docx", file=sys.stderr)
        return 2
    return app.run()
