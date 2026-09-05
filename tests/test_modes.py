"""双模式分发与 GUI 纯逻辑的单元测试。"""

from thesislint import gui
from thesislint.cli import main


class _FakeWidget:
    def __init__(self, mapped=False, children=None, **config):
        self.mapped = mapped
        self.children = children or []
        self.config = config
        self.calls = []
        self.tags = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def pack(self, **kwargs):
        self.mapped = True
        self.calls.append(("pack", kwargs))

    def pack_forget(self):
        self.mapped = False
        self.calls.append(("pack_forget", {}))

    def winfo_ismapped(self):
        return self.mapped

    def winfo_children(self):
        return self.children

    def cget(self, option):
        if option not in self.config:
            raise KeyError(option)
        return self.config[option]

    def delete(self, *args):
        self.calls.append(("delete", args))

    def insert(self, *args):
        self.calls.append(("insert", args))

    def focus_set(self):
        self.calls.append(("focus_set", {}))

    def tag_configure(self, tag, **kwargs):
        self.tags.setdefault(tag, {}).update(kwargs)


class TestGuiPureHelpers:
    def test_result_meta_reflects_outcome(self):
        assert gui._result_meta(True, 0, 0, 1) == ("✓", "全部通过", gui.OK)
        assert gui._result_meta(True, 2, 0, 1) == ("×", "发现 2 个错误", gui.ERR)
        assert gui._result_meta(True, 0, 3, 1) == ("!", "发现 3 个警告", gui.WARN)
        assert gui._result_meta(False, 0, 0, 0) == ("—", "未找到参考文献章节", gui.ERR)
        assert gui._result_meta(True, 0, 0, 0) == ("—", "未提取到参考文献条目", gui.WARN)

    def test_drop_paths_use_tcl_list_parser(self):
        paths = gui._split_drop_paths(
            "ignored raw data",
            lambda _data: (r"C:\论文 一.docx", r"D:\论文二.docx"),
        )
        assert paths == [r"C:\论文 一.docx", r"D:\论文二.docx"]

    def test_drop_paths_have_single_path_fallback(self):
        def broken_parser(_data):
            raise ValueError("bad Tcl list")

        assert gui._split_drop_paths(r"{C:\论文 一.docx}", broken_parser) == [r"C:\论文 一.docx"]

    def test_stage_colors_follow_progress(self):
        app = gui.App.__new__(gui.App)
        app.step_labels = [_FakeWidget(), _FakeWidget(), _FakeWidget()]
        app._set_stage(2, completed=1)
        assert [label.config["fg"] for label in app.step_labels] == [
            gui.OK,
            gui.ACCENT_HI,
            gui.FAINT,
        ]

    def test_drop_state_shows_only_requested_panel(self):
        app = gui.App.__new__(gui.App)
        app.hero = _FakeWidget(mapped=True)
        app.busy = _FakeWidget()
        app.done = _FakeWidget()

        app._show_drop_state("busy")
        assert not app.hero.mapped and app.busy.mapped and not app.done.mapped
        app._show_drop_state("done")
        assert not app.hero.mapped and not app.busy.mapped and app.done.mapped
        app._show_drop_state("idle")
        assert app.hero.mapped and not app.busy.mapped and not app.done.mapped

    def test_clear_result_views_resets_caches_and_panels(self):
        app = gui.App.__new__(gui.App)
        app._text_cache = "old"
        app._md_cache = "old"
        app._fix_cache = "old"
        app._report_views = {"all": "old"}
        app._report_filter = "warn"
        app.stats_bar = _FakeWidget(mapped=True)
        app.fix_panel = _FakeWidget(mapped=True)
        app.report_box = _FakeWidget()
        app.toolbar = _FakeWidget(mapped=True)
        app.report = _FakeWidget()
        app.btn_fix = _FakeWidget()

        app._clear_result_views()

        assert app._text_cache == ""
        assert app._md_cache is None
        assert app._fix_cache == ""
        assert app._report_views == {"all": "", "error": "", "warn": ""}
        assert app._report_filter == "all"
        assert not app.stats_bar.mapped and not app.fix_panel.mapped
        assert app.report.config["state"] == "disabled"
        assert app.btn_fix.config["text"] == "生成修正后列表"
        assert any(call[0] == "insert" for call in app.report.calls)

    def test_report_filter_changes_visible_text_but_keeps_full_copy_cache(self):
        app = gui.App.__new__(gui.App)
        app._palette = gui.DARK_THEME
        app._text_cache = "完整报告"
        app._report_views = {"all": "完整报告", "error": "仅错误", "warn": "仅警告"}
        app._report_filter = "all"
        app.report = _FakeWidget()
        app.report_filter_buttons = {
            "all": _FakeWidget(),
            "error": _FakeWidget(),
            "warn": _FakeWidget(),
        }

        app._select_report_filter("error")

        inserted = "".join(call[1][1] for call in app.report.calls if call[0] == "insert")
        assert inserted == "仅错误"
        assert app._text_cache == "完整报告"
        assert app._report_filter == "error"

    def test_escape_collapses_fix_panel_and_focuses_report(self):
        app = gui.App.__new__(gui.App)
        app.fix_panel = _FakeWidget(mapped=True)
        app.report_box = _FakeWidget()
        app.toolbar = _FakeWidget(mapped=True)
        app.report = _FakeWidget()
        app.step_labels = [_FakeWidget(), _FakeWidget(), _FakeWidget()]

        app._collapse_fix_panel()

        assert not app.fix_panel.mapped
        assert app.report_box.mapped
        assert any(call[0] == "focus_set" for call in app.report.calls)

    def test_current_job_failure_returns_to_file_selection(self):
        app = gui.App.__new__(gui.App)
        app._job_id = 7
        app._last_path = r"C:\论文.docx"
        app.hero = _FakeWidget()
        app.busy = _FakeWidget(mapped=True)
        app.done = _FakeWidget()
        app.step_labels = [_FakeWidget(), _FakeWidget(), _FakeWidget()]
        app.report = _FakeWidget()
        app.status = _FakeWidget()

        app._finish_error(7, "文档损坏")

        assert app._last_path is None
        assert app.hero.mapped and not app.busy.mapped
        assert "请选择另一份" in app.status.config["text"]
        inserted = "".join(call[1][1] for call in app.report.calls if call[0] == "insert")
        assert "文档损坏" in inserted

    def test_light_theme_recolors_widgets_and_report_tags(self):
        child = _FakeWidget(background=gui.SURFACE, foreground=gui.TEXT)
        app = gui.App.__new__(gui.App)
        app.root = _FakeWidget(children=[child], background=gui.BG)
        app._theme_name = "dark"
        app._palette = gui.DARK_THEME
        app._themed_buttons = []
        app.report = _FakeWidget()
        app.fix_text = _FakeWidget()
        app.btn_theme = _FakeWidget()
        app._ttk = object()
        app._style_ttk = lambda _ttk: None
        app._apply_titlebar_theme = lambda: None

        app._apply_theme("light")

        assert app._theme_name == "light"
        assert app.root.config["background"] == gui.LIGHT_THEME["BG"]
        assert child.config["background"] == gui.LIGHT_THEME["SURFACE"]
        assert child.config["foreground"] == gui.LIGHT_THEME["TEXT"]
        assert app.report.tags["err"]["foreground"] == gui.LIGHT_THEME["ERR"]
        assert app.btn_theme.config["text"] == "深色"

    def test_runtime_dark_color_resolves_to_current_theme(self):
        app = gui.App.__new__(gui.App)
        app._palette = gui.LIGHT_THEME
        assert app._resolve_color(gui.ERR) == gui.LIGHT_THEME["ERR"]


class TestShouldLaunchGui:
    def test_no_args_means_gui(self, monkeypatch):
        monkeypatch.setattr(gui, "_supports_tk", lambda: True)
        assert gui.should_launch_gui([]) is True

    def test_flags_mean_cli(self, monkeypatch):
        monkeypatch.setattr(gui, "_supports_tk", lambda: True)
        assert gui.should_launch_gui(["--format", "md", "a.docx"]) is False
        assert gui.should_launch_gui(["--help"]) is False

    def test_docx_arg_respects_explorer_detection(self, monkeypatch):
        monkeypatch.setattr(gui, "_supports_tk", lambda: True)
        monkeypatch.setattr(gui, "_launched_from_explorer", lambda: True)
        assert gui.should_launch_gui([r"C:\论文\a.docx"]) is True

        monkeypatch.setattr(gui, "_launched_from_explorer", lambda: False)
        assert gui.should_launch_gui([r"C:\论文\a.docx"]) is False

    def test_terminal_flag_beats_docx(self, monkeypatch):
        monkeypatch.setattr(gui, "_supports_tk", lambda: True)
        monkeypatch.setattr(gui, "_launched_from_explorer", lambda: True)
        assert gui.should_launch_gui(["--strict"]) is False

    def test_no_tk_means_never_gui(self, monkeypatch):
        monkeypatch.setattr(gui, "_supports_tk", lambda: False)
        assert gui.should_launch_gui([]) is False


class TestCliStillWorks:
    """确保 GUI 分发没有破坏命令行行为。"""

    def test_main_with_args_returns_report(self, capsys):
        # 带参数：不应该进入 GUI（_supports_tk 即便为 True 也不走）
        code = main(["nonexistent.docx"])
        assert code == 2

    def test_help_flag_skips_gui(self, capsys, monkeypatch):
        monkeypatch.setattr(gui, "_supports_tk", lambda: True)
        try:
            main(["--help"])
        except SystemExit as e:
            assert e.code == 0
        out = capsys.readouterr().out
        assert "thesislint" in out
