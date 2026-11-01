"""桌面工作流：文件传递、报告快照、过期回调与导出失败。"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from thesislint import cli, gui


def test_make_root_uses_supported_drag_and_drop_api(monkeypatch):
    registered = []
    root = SimpleNamespace(
        drop_target_register=lambda value: registered.append(value),
        dnd_bind=lambda event, callback: registered.append((event, callback)),
    )
    monkeypatch.setitem(
        sys.modules,
        "tkinterdnd2",
        SimpleNamespace(
            DND_FILES="DND_Files",
            TkinterDnD=SimpleNamespace(Tk=lambda: root),
        ),
    )
    app = gui.App.__new__(gui.App)
    fallback = object()
    assert app._make_root(SimpleNamespace(Tk=lambda: fallback)) is root
    assert registered == ["DND_Files", ("<<Drop>>", app._on_drop)]


def test_make_root_still_works_when_drag_library_is_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "tkinterdnd2", None)
    root = object()
    app = gui.App.__new__(gui.App)
    assert app._make_root(SimpleNamespace(Tk=lambda: root)) is root


@pytest.mark.parametrize("failure_at", ["register", "bind"])
def test_drag_setup_failure_destroys_partial_root_before_fallback(monkeypatch, failure_at):
    events = []

    def setup(step):
        events.append(step)
        if step == failure_at:
            raise RuntimeError("synthetic TkDnD setup failure")

    partial_root = SimpleNamespace(
        drop_target_register=lambda _kind: setup("register"),
        dnd_bind=lambda _event, _callback: setup("bind"),
        destroy=lambda: events.append("destroy"),
    )
    monkeypatch.setitem(
        sys.modules,
        "tkinterdnd2",
        SimpleNamespace(DND_FILES="DND_Files", TkinterDnD=SimpleNamespace(Tk=lambda: partial_root)),
    )
    fallback = object()

    def plain_root():
        events.append("fallback")
        return fallback

    app = gui.App.__new__(gui.App)
    assert app._make_root(SimpleNamespace(Tk=plain_root)) is fallback
    assert events == (["register"] if failure_at == "register" else ["register", "bind"]) + [
        "destroy",
        "fallback",
    ]


def test_fix_thread_start_failure_preserves_results_and_allows_retry(monkeypatch):
    app = gui.App.__new__(gui.App)
    app._entry_snapshot = ("[4] 原始文献",)
    app._preserve_numbers_snapshot = True
    app._job_id = 1
    app._text_cache = "原检查报告"
    app._fix_cache = "上次修正列表"
    options = {"state": "normal", "takefocus": True}
    app.btn_fix = SimpleNamespace(configure=options.update)
    stages, messages, started = [], [], []
    app._set_stage = lambda stage, **kw: stages.append(stage)
    app._set_status = lambda message, color: messages.append((message, color))
    app._fix_work = lambda *args: started.append(args)

    def cannot_start():
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(
        gui.threading, "Thread", lambda **kwargs: SimpleNamespace(start=cannot_start)
    )
    app.generate_fix()

    assert not started
    assert options == {"state": "normal", "takefocus": True}
    assert stages[-1] == 2
    assert messages[-1][1] == gui.ERR
    assert "生成失败" in messages[-1][0]
    assert app._text_cache == "原检查报告"
    assert app._fix_cache == "上次修正列表"

    monkeypatch.setattr(
        gui.threading,
        "Thread",
        lambda *, target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    app.generate_fix()
    assert started == [(app._entry_snapshot, 1, True)]


def test_empty_document_is_not_shown_as_passed(tmp_path):
    path = tmp_path / "empty.docx"
    doc = Document()
    doc.add_heading("参考文献", level=1)
    doc.save(path)
    app = gui.App.__new__(gui.App)
    callbacks = []
    finished = []
    app._closed = False
    app._ui_callbacks = SimpleNamespace(put=callbacks.append)
    app.root = SimpleNamespace(after=lambda delay, callback: callbacks.append(callback))
    app._finish = lambda *args: finished.append(args)
    app._work(str(path), path.name, 1)
    callbacks.pop(0)()
    assert "未提取到" in finished[0][5]
    assert finished[0][6] != gui.OK


@pytest.mark.parametrize("args", [[], ["含空格的 论文.docx"]])
def test_explorer_launch_forwards_file(monkeypatch, args):
    received = []
    monkeypatch.setattr(gui, "should_launch_gui", lambda _args: True)
    monkeypatch.setattr(
        gui, "run_gui", lambda initial_path=None: received.append(initial_path) or 0
    )
    assert cli.main(args) == 0
    assert received == ([Path(args[0])] if args else [None])


def test_run_gui_schedules_initial_file(monkeypatch):
    scheduled = []
    opened = []
    app = SimpleNamespace(
        _schedule=lambda delay, callback: scheduled.append(callback),
        check=opened.append,
        run=lambda: 0,
    )
    monkeypatch.setattr(gui, "_supports_tk", lambda: True)
    monkeypatch.setattr(gui, "App", lambda: app)
    assert gui.run_gui(Path("论文.docx")) == 0
    assert not opened
    scheduled[0]()
    assert opened == ["论文.docx"]


@pytest.mark.parametrize(
    "body,extra_entry",
    [
        (None, None),
        ("已有研究见文献[4]，待核对的引用见[9]。", None),
        ("已有研究见文献[4]。", "李四. 缺号标题[J]. 学报, 2024"),
        ("已有研究见文献[4]。", "[4] 李四. 重号标题[J]. 学报, 2024"),
        ("正文没有可识别的引用编号。", None),
        ("正文引用使用了超出支持范围的[1000]。", None),
    ],
)
def test_fix_uses_displayed_report_after_source_changes(tmp_path, monkeypatch, body, extra_entry):
    path = tmp_path / "论文.docx"
    doc = Document()
    if body:
        doc.add_paragraph(body)
    doc.add_heading("参考文献", level=1)
    original = f"[{4 if body else 1}] 张三. 原始标题[J]. 学报, 2024"
    if extra_entry:
        doc.add_paragraph(extra_entry)
    doc.add_paragraph(original)
    doc.save(path)
    app = gui.App.__new__(gui.App)
    callbacks = []
    app._closed = False
    app._ui_callbacks = SimpleNamespace(put=callbacks.append)
    app.root = SimpleNamespace(after=lambda delay, callback: callbacks.append(callback))
    app._job_id = 1
    app._last_path = str(path)
    app._entry_snapshot = ()

    # 只替换渲染控件；保留真实 _finish 的快照接收及过期任务判断。
    app._text_cache = ""
    app._md_cache = None
    widget = SimpleNamespace(
        configure=lambda **kw: None,
        pack=lambda **kw: None,
        delete=lambda *args: None,
        insert=lambda *args: None,
    )
    app.done_name = app.report = app.stats_bar = app.toolbar = widget
    app.btn_fix = app.btn_copy = app.btn_md = widget
    app.stat_values = dict.fromkeys(("total", "errors", "warns"), widget)
    app._show_drop_state = lambda mode: None
    app._set_stage = lambda *args, **kw: None
    app._set_status = lambda *args: None
    app._auto_fix_pending = False
    app._work(str(path), path.name, 1)
    callbacks.pop(0)()
    expected_entries = (extra_entry, original) if extra_entry else (original,)
    assert app._entry_snapshot == expected_entries
    assert app._preserve_numbers_snapshot is bool(body)
    if extra_entry:
        assert cli.analyze(path).citations.checked is False
        assert "无法可靠映射" in app._text_cache
    elif body and "[9]" in body:
        app._select_report_filter("error")
        assert "S003" not in app._report_views["error"]
        assert "S003" in app._report_views["warn"]
        assert "S003" in app._text_cache
        assert "S003" in app._md_cache

    # 用户在 Word 中另存了新内容；当前报告仍应对应旧内容。
    doc.paragraphs[-1].text = "[1] 李四. 后来修改的标题[J]. 学报, 2025."
    if body:
        doc.paragraphs[0].text = "新正文没有引用编号。"
    doc.save(path)
    finished = []
    app._finish_fix = lambda *args: finished.append(args)
    monkeypatch.setattr(
        gui.threading,
        "Thread",
        lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args)),
    )
    app.generate_fix()
    callbacks.pop(0)()
    assert "原始标题" in finished[0][3]
    assert "后来修改" not in finished[0][3]
    assert finished[0][3].splitlines()[-1].startswith("[4]" if body else "[1]")
    assert ("保留文献编号" in finished[0][2]) is bool(body)
    if extra_entry:
        assert finished[0][3].splitlines()[0] == extra_entry + "."


def test_new_check_clears_citation_snapshot_and_filtered_reports():
    app = gui.App.__new__(gui.App)
    app._entry_snapshot = ("旧文献",)
    app._preserve_numbers_snapshot = True
    app._text_cache = app._md_cache = app._fix_cache = "旧报告"
    app._report_filter = "warn"
    widget = SimpleNamespace(
        configure=lambda **kw: None,
        pack_forget=lambda: None,
        delete=lambda *args: None,
        insert=lambda *args: None,
    )
    app.stats_bar = app.report = app.btn_fix = widget
    app._show_report_panel = lambda: None
    app._clear_result_views()
    assert app._entry_snapshot == ()
    assert app._preserve_numbers_snapshot is False
    assert app._report_filter == "all"
    assert not any(app._report_views.values())
    assert app._text_cache == app._fix_cache == ""
    assert app._md_cache is None


@pytest.mark.parametrize(
    "method,args",
    [
        ("_finish", (1, "旧文档.docx", "", "", "", "", "", True, {}, (), {}, True)),
        ("_finish_error", (1, "旧错误")),
        ("_finish_fix_error", (1, "旧错误")),
        ("_finish_fix", (1, "旧修正", "旧统计", "旧内容", 0)),
    ],
)
def test_stale_callbacks_cannot_touch_new_job(method, args):
    app = gui.App.__new__(gui.App)
    app._job_id = 2
    app._fix_cache = "新内容"
    app._preserve_numbers_snapshot = False
    getattr(app, method)(*args)
    assert app._fix_cache == "新内容"
    assert app._preserve_numbers_snapshot is False


@pytest.mark.parametrize(
    "method,cache", [("export_md", "_md_cache"), ("export_fix_txt", "_fix_cache")]
)
def test_export_permission_error_has_recovery_message(monkeypatch, method, cache):
    app = gui.App.__new__(gui.App)
    setattr(app, cache, "待导出的内容")
    app._filedialog = SimpleNamespace(asksaveasfilename=lambda **kw: "report.txt")
    messages = []
    app._set_status = lambda message, color: messages.append(message)

    def denied(*args, **kwargs):
        raise PermissionError("文件被占用")

    monkeypatch.setattr(Path, "write_text", denied)
    getattr(app, method)()
    assert "导出失败" in messages[-1]
    assert "位置" in messages[-1]
    assert getattr(app, cache) == "待导出的内容"
