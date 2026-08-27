"""双模式分发与 GUI 纯逻辑的单元测试。"""

import sys

from thesislint import gui
from thesislint.cli import main


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
