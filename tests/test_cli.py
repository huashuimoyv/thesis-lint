"""CLI 退出码契约测试。

背景：README 承诺 `--strict` 可用于 CI（有警告也算失败），
但 v0.4.0 中退出码路径（cli.py:87-101）零测试覆盖。
本文件把「退出码契约」钉死。
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from docx import Document

from thesislint import gui
from thesislint.cli import main


@pytest.fixture(autouse=True)
def _force_cli_mode(monkeypatch):
    """强制走命令行分支，避免在装有 tkinter 的机器上误开 GUI 导致测试卡死。

    cli.main 内部是 `from .gui import should_launch_gui`，
    should_launch_gui 又调用模块级 _supports_tk()，所以 patch 模块属性即可生效。
    与 tests/test_modes.py 的做法保持一致。
    """
    monkeypatch.setattr(gui, "_supports_tk", lambda: False)


def _make_docx(path, entries: list[str], heading: str = "参考文献"):
    doc = Document()
    doc.add_heading(heading, level=1)
    for e in entries:
        doc.add_paragraph(e)
    doc.save(str(path))
    return path


class TestExitCodes:
    def test_institution_author_passes_strict_without_changing_source(self, tmp_path, capsys):
        entry = "[1] World Health Organization. Global health report[R]. Geneva, 2024."
        path = _make_docx(tmp_path / "institution.docx", [entry])
        original = path.read_bytes()

        assert main([str(path), "--strict", "--format", "json"]) == 0

        data = json.loads(capsys.readouterr().out)
        assert data["entries"][0]["text"] == entry
        assert data["warn_count"] == 0
        assert path.read_bytes() == original

    def test_clean_doc_returns_zero(self, tmp_path):
        path = _make_docx(
            tmp_path / "clean.docx",
            [
                "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
                "[2] 李四. 文二[M]. 北京: 出版社, 2020: 1-9.",
            ],
        )
        assert main([str(path)]) == 0

    def test_error_returns_one(self, tmp_path):
        path = _make_docx(
            tmp_path / "err.docx",
            [
                "张三. 无序号无类型的条目. 学报, 2024.",  # E001 + E002
            ],
        )
        assert main([str(path)]) == 1

    def test_warning_returns_zero_without_strict(self, tmp_path):
        path = _make_docx(
            tmp_path / "warn.docx",
            [
                "[1] 张三，李四. 论文名称[J]. 学报，2024，1(1): 1-9.",  # W005 全角
            ],
        )
        assert main([str(path)]) == 0

    def test_warning_returns_one_with_strict(self, tmp_path):
        path = _make_docx(
            tmp_path / "warn.docx",
            [
                "[1] 张三，李四. 论文名称[J]. 学报，2024，1(1): 1-9.",  # W005 全角
            ],
        )
        assert main([str(path), "--strict"]) == 1

    def test_duplicate_number_returns_one(self, tmp_path):
        path = _make_docx(
            tmp_path / "dup.docx",
            [
                "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
                "[1] 李四. 文二[J]. 学报, 2024, 2(1): 1-9.",  # S002
            ],
        )
        assert main([str(path)]) == 1


class TestFixedOutput:
    def test_reference_list_can_be_saved_even_if_source_has_errors(self, tmp_path, capsys):
        path = _make_docx(tmp_path / "refs.docx", ["张三. 题名[J]. 学报, 2024"], "References")
        original = path.read_bytes()
        assert main([str(path), "--section", "References", "--format", "fixed"]) == 1
        streams = capsys.readouterr()
        assert streams.out == "[1] 张三. 题名[J]. 学报, 2024.\n"
        assert "原文" in streams.err and "1 个错误" in streams.err
        assert path.read_bytes() == original

    @pytest.mark.parametrize("body", ["研究依据见 [4]。", "本文使用作者—年份引用。"])
    def test_body_protects_numbers_and_manual_notes_go_to_stderr(self, tmp_path, capsys, body):
        doc = Document()
        doc.add_paragraph(body)
        doc.add_heading("参考文献", level=1)
        doc.add_paragraph("[4] 张三. 题名[J]. 学报, 2024")
        path = tmp_path / "保留序号.docx"
        doc.save(path)
        assert main([str(path), "--format", "fixed"]) == 0
        streams = capsys.readouterr()
        assert streams.out == "[4] 张三. 题名[J]. 学报, 2024.\n"
        assert "第 1 条" in streams.err and "保留原序号" in streams.err

    @pytest.mark.parametrize("strict,expected", [([], 0), (["--strict"], 1)])
    def test_missing_citation_affects_source_status(self, tmp_path, capsys, strict, expected):
        doc = Document()
        doc.add_paragraph("引用[1]和[9]。")
        doc.add_heading("参考文献", level=1)
        entry = "[1] 张三. 题名[J]. 学报, 2024."
        doc.add_paragraph(entry)
        path = tmp_path / "citation.docx"
        doc.save(path)
        assert main([str(path), "--format", "fixed", *strict]) == expected
        streams = capsys.readouterr()
        assert streams.out == entry + "\n"
        assert "1 个警告" in streams.err and "S003" in streams.err

    @pytest.mark.parametrize("heading", [None, "参考文献", "绪论"])
    def test_unavailable_or_missing_input_has_empty_stdout(self, tmp_path, capsys, heading):
        args = ["--format", "fixed"]
        if heading:
            args.append(str(_make_docx(tmp_path / "empty.docx", [], heading)))
        assert main(args) == 2
        streams = capsys.readouterr()
        assert streams.out == ""
        assert streams.err.strip()


class TestUsageErrors:
    def test_help_is_utf8_in_windows_subprocess(self):
        completed = subprocess.run(
            [sys.executable, "-m", "thesislint.cli", "--help"],
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0
        assert "毕业论文" in completed.stdout.decode("utf-8")

    def test_missing_file_returns_two(self):
        assert main(["nonexistent.docx"]) == 2

    def test_wrong_extension_returns_two(self, tmp_path):
        p = tmp_path / "a.pdf"
        p.write_bytes(b"%PDF-1.4")
        assert main([str(p)]) == 2

    @pytest.mark.parametrize("heading", ["绪论", "参考文献"])
    @pytest.mark.parametrize("fmt", ["text", "md", "json"])
    def test_uncheckable_document_returns_two(self, tmp_path, capsys, heading, fmt):
        path = _make_docx(tmp_path / "empty.docx", [], heading=heading)
        assert main([str(path), "--format", fmt]) == 2
        output = capsys.readouterr().out
        assert "未找到" in output or "未提取到" in output
        assert "0 条通过" not in output
