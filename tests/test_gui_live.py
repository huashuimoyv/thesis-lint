"""显式启用的真实 Tk 集成检查：THESISLINT_RUN_GUI_TESTS=1 pytest tests/test_gui_live.py。"""

import os
import threading
from types import SimpleNamespace

import pytest
from docx import Document

from thesislint import gui

pytestmark = pytest.mark.skipif(
    os.environ.get("THESISLINT_RUN_GUI_TESTS") != "1",
    reason="真实 Tk 测试需桌面环境并显式启用",
)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_report_filter_selection_survives_hover_and_theme_change(monkeypatch, theme):
    for key in ("THESISLINT_GUI_AUTODEMO", "THESISLINT_GUI_AUTOFIX", "THESISLINT_GUI_AUTOCLOSE_MS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("THESISLINT_GUI_THEME", theme)
    app = gui.App()
    app.root.withdraw()
    try:
        app._report_views = {key: key for key in ("all", "error", "warn")}
        for button in app.report_filter_buttons.values():
            app._set_enabled(button, True)
        for selected in app.report_filter_buttons:
            app._select_report_filter(selected)
            for _ in range(2):
                for button in app.report_filter_buttons.values():
                    for sequence in ("<Enter>", "<Leave>"):
                        # 隐藏窗口不接收鼠标事件，直接调用控件实际注册的 Tk 回调。
                        callback = button.bind(sequence).split("[", 1)[1].split()[0]
                        button.tk.call(callback, *("0",) * len(button._subst_format))
                        active = app.report_filter_buttons[selected]
                        assert app._report_filter == selected
                        assert active.cget("bg") == app._color("PAPER")
                        assert active.cget("fg") == app._color("ACCENT_HI")
                        assert active.cget("activebackground") == app._color("PAPER")
                        assert active.cget("activeforeground") == app._color("ACCENT_HI")
                        assert active.cget("highlightbackground") == app._color("ACCENT")
                    if button is not active:
                        assert button.cget("bg") == app._color("RAISE")
                        assert button.cget("fg") == app._color("TEXT")
                        assert button.cget("highlightbackground") == app._color("RAISE")
                app.toggle_theme()
        assert app._theme_name == theme
    finally:
        app.root.destroy()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_launch_analyze_fix_and_export(tmp_path, monkeypatch, theme):
    for key in ("THESISLINT_GUI_AUTODEMO", "THESISLINT_GUI_AUTOFIX", "THESISLINT_GUI_AUTOCLOSE_MS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("THESISLINT_GUI_THEME", theme)
    path = tmp_path / "含空格的 论文.docx"
    output = tmp_path / "修正后.txt"
    doc = Document()
    doc.add_paragraph("研究依据见[4]，待核对的引用见[9]。")
    doc.add_heading("参考文献", level=1)
    doc.add_paragraph("[4] 张三. 原始标题[J]. 学报, 2024\n[7] 李四. 文二[J]. 学报, 2023.")
    doc.save(path)
    real_app = gui.App
    errors = []
    finished = []

    def create_app():
        app = real_app()
        app.root.withdraw()
        assert hasattr(app.root, "drop_target_register")
        assert hasattr(app.root, "dnd_bind")
        app._filedialog = SimpleNamespace(asksaveasfilename=lambda **kw: str(output))

        def callback_failed(_kind, error, _traceback):
            errors.append(error)
            app.root.destroy()

        app.root.report_callback_exception = callback_failed

        def verify_fix():
            if not app._fix_cache:
                app.root.after(25, verify_fix)
                return
            assert "原始标题" in app._fix_cache
            assert "后来修改" not in app._fix_cache
            assert app._fix_cache.startswith("[4]")
            assert "\n[7]" in app._fix_cache
            assert "保留文献编号" in app.fix_stats.cget("text")
            app.export_fix_txt()
            assert output.read_text(encoding="utf-8") == app._fix_cache
            app.toggle_theme()
            app.toggle_theme()
            assert app._theme_name == theme
            assert app.report.cget("background") == app._color("SURFACE")
            assert app.fix_text.tag_cget("warn", "foreground") == app._color("WARN")
            finished.append(True)
            app.root.destroy()

        def verify_report():
            if not app._entry_snapshot:
                app.root.after(25, verify_report)
                return
            assert len(app._entry_snapshot) == 2
            assert app._last_path == str(path)
            assert app._preserve_numbers_snapshot is True
            app._select_report_filter("warn")
            assert app._report_filter == "warn"
            assert "[WARN ]" in app.report.get("1.0", "end")
            assert app._text_cache == app._report_views["all"]
            assert "S003" in app.report.get("1.0", "end")
            app._select_report_filter("error")
            assert "S003" not in app.report.get("1.0", "end")
            assert "S003" in app._text_cache
            assert "S003" in app._md_cache
            doc.paragraphs[0].text = "新正文没有引用编号。"
            doc.paragraphs[-1].text = "[1] 张三. 后来修改[J]. 学报, 2025."
            doc.save(path)
            app.generate_fix()
            app.root.after(25, verify_fix)

        def timeout():
            errors.append(TimeoutError("桌面检查和导出流程未在 10 秒内完成"))
            app.root.destroy()

        app.root.after(25, verify_report)
        app.root.after(10000, timeout)
        return app

    monkeypatch.setattr(gui, "App", create_app)
    assert gui.run_gui(path) == 0
    assert not errors, errors
    assert finished == [True]


@pytest.mark.parametrize("operation", ["analysis", "fix"])
@pytest.mark.parametrize("fails", [False, True])
def test_worker_finishing_after_window_close_never_calls_tk(
    tmp_path, monkeypatch, operation, fails
):
    from thesislint import cli, fixer

    for key in ("THESISLINT_GUI_AUTODEMO", "THESISLINT_GUI_AUTOFIX", "THESISLINT_GUI_AUTOCLOSE_MS"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "close-during-work.docx"
    document = Document()
    document.add_heading("参考文献", level=1)
    document.add_paragraph("[1] 张三. 文献[J]. 学报, 2024.")
    document.save(path)
    app = gui.App()
    app.root.withdraw()
    entered = threading.Event()
    release = threading.Event()
    errors = []
    worker_tk_calls = []
    main_thread = threading.get_ident()
    original_after = app.root.after

    def record_after(*args):
        if threading.get_ident() != main_thread:
            worker_tk_calls.append(args[0])
        return original_after(*args)

    monkeypatch.setattr(app.root, "after", record_after)
    original = cli.analyze if operation == "analysis" else fixer.fix_entries

    def blocked(*args, **kwargs):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("未收到测试释放信号")
        if fails:
            raise ValueError("测试中的解析/修正失败")
        return original(*args, **kwargs)

    if operation == "analysis":
        monkeypatch.setattr(cli, "analyze", blocked)

        def target():
            app._work(str(path), path.name, 1)

    else:
        monkeypatch.setattr(fixer, "fix_entries", blocked)

        def target():
            app._fix_work((document.paragraphs[-1].text,), 1)

    def run_worker():
        try:
            target()
        except Exception as error:  # noqa: BLE001  将后台异常带回主线程进行断言
            errors.append(error)

    worker = threading.Thread(target=run_worker, daemon=True)
    worker.start()
    try:
        assert entered.wait(3), "后台工作没有启动"
        app.root.destroy()
    finally:
        release.set()
        worker.join(4)

    assert not worker.is_alive(), "窗口关闭后工作线程未结束"
    assert not errors, errors
    assert worker_tk_calls == []


def test_root_close_discards_queued_results_and_timers_but_child_close_does_not(monkeypatch):
    for key in ("THESISLINT_GUI_AUTODEMO", "THESISLINT_GUI_AUTOFIX", "THESISLINT_GUI_AUTOCLOSE_MS"):
        monkeypatch.delenv(key, raising=False)
    app = gui.App()
    app.root.withdraw()
    rendered = []
    errors = []
    app.root.report_callback_exception = lambda _type, error, _tb: errors.append(error)
    app._post_ui(lambda: rendered.append(True))
    scheduled = set(app._after_ids)
    job_id = app._job_id
    app._tk.Label(app.root).destroy()
    assert not app._closed
    assert app._job_id == job_id
    assert not app._ui_callbacks.empty()

    app.root.destroy()
    app._drain_ui_callbacks()

    assert app._closed
    assert app._job_id != job_id
    assert app._ui_callbacks.empty()
    assert not app._after_ids
    assert not scheduled.intersection(app.root.tk.call("after", "info"))
    assert not rendered
    assert not errors


def test_immediate_close_cancels_initial_file_callback(tmp_path, monkeypatch):
    for key in ("THESISLINT_GUI_AUTODEMO", "THESISLINT_GUI_AUTOFIX"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("THESISLINT_GUI_AUTOCLOSE_MS", "0")
    app = gui.App()
    app.root.withdraw()
    opened = []
    app.check = opened.append
    # Tk 删除 Python 回调命令后，残留 after 由 Tcl bgerror 报错，而非 Python 异常回调。
    app.root.tk.eval(
        "set ::close_errors {}; proc bgerror {message} {lappend ::close_errors $message}"
    )
    monkeypatch.setattr(gui, "App", lambda: app)

    assert gui.run_gui(tmp_path / "not-opened.docx") == 0
    app.root.tk.call("update")
    background_errors = app.root.tk.eval("set ::close_errors")

    assert app._closed
    assert not opened
    assert "invalid command name" not in background_errors


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_export_and_clipboard_error_recovery_in_real_widgets(tmp_path, monkeypatch, theme):
    for key in ("THESISLINT_GUI_AUTODEMO", "THESISLINT_GUI_AUTOFIX", "THESISLINT_GUI_AUTOCLOSE_MS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("THESISLINT_GUI_THEME", theme)
    source = tmp_path / "应保护的 论文.docx"
    document = Document()
    document.add_paragraph("原始论文不得被报告覆盖")
    document.save(source)
    original = source.read_bytes()
    app = gui.App()
    app.root.withdraw()
    errors = []
    app.root.report_callback_exception = lambda _kind, error, _tb: errors.append(error)
    app._last_path = str(source)
    app._text_cache = "完整报告"
    app._md_cache = "# 完整报告"
    app._fix_cache = "[4] 保留编号的文献."
    app._filedialog = SimpleNamespace(asksaveasfilename=lambda **kw: str(source))
    try:
        for button in (app.btn_md, app.btn_fix_txt):
            app._set_enabled(button, True)
            button.invoke()
            assert source.read_bytes() == original
            assert "覆盖" in app.status.cget("text")
            assert app.status.cget("fg") == app._color("ERR")

        def denied(*args):
            raise app._tk.TclError("clipboard unavailable")

        for button, expected in (
            (app.btn_copy, app._text_cache),
            (app.btn_fix_copy, app._fix_cache),
        ):
            app._set_enabled(button, True)
            for fails_at in ("clipboard_clear", "clipboard_append"):
                # Never clear, read or modify the user's actual clipboard.
                monkeypatch.setattr(app.root, "clipboard_clear", lambda: None)
                monkeypatch.setattr(app.root, "clipboard_append", lambda value: None)
                monkeypatch.setattr(app.root, fails_at, denied)
                button.invoke()
                assert "复制失败" in app.status.cget("text")
                assert app.status.cget("fg") == app._color("WARN")
                assert not errors
            copied = []
            monkeypatch.setattr(app.root, "clipboard_clear", lambda: None)
            monkeypatch.setattr(app.root, "clipboard_append", copied.append)
            button.invoke()
            assert copied == [expected]
            assert app.status.cget("fg") == app._color("OK")
        assert not errors
    finally:
        app.root.destroy()
