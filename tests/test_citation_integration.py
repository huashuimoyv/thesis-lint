"""正文引用核对在 CLI、报告格式、计数及退出码之间的信息一致性。"""

import json

import pytest
from docx import Document

from thesislint import gui
from thesislint.cli import analyze, main
from thesislint.fixer import fix_entries
from thesislint.report import build_json_report, build_markdown_report, build_text_report


def _document(path, body, numbers=(1, 2, 3), heading="参考文献"):
    doc = Document()
    for paragraph in body:
        doc.add_paragraph(paragraph)
    doc.add_heading(heading, level=1)
    for number in numbers:
        doc.add_paragraph(f"[{number}] 张三. 文献题名[J]. 学报, 2024, 1(1): 1-9.")
    doc.save(path)
    return path


def test_citation_details_survive_all_formats_and_filters(tmp_path):
    report = analyze(_document(tmp_path / "论文.docx", ["已有方法[2]。后续结果[1,9]。"]))
    data = json.loads(build_json_report(report))
    codes = {issue["code"] for issue in data["citations"]["issues"]}
    assert codes == {"S003", "S004", "S005"}
    text = build_text_report(report)
    markdown = build_markdown_report(report)
    for code in codes:
        assert code in text
        assert code in markdown
        assert code in build_text_report(report, level="WARN")
        assert code not in build_text_report(report, level="ERROR")
    assert "正文引用核对" in text and "正文引用核对" in markdown
    assert data["citations"]["checked"]
    assert data["citations"]["citations"][0]["line"] == 1
    assert data["citations"]["citations"][0]["numbers"] == [2]
    details = (
        [issue for entry in data["entries"] for issue in entry["issues"]]
        + data["section_issues"]
        + data["citations"]["issues"]
    )
    assert data["warn_count"] == sum(issue["level"] == "WARN" for issue in details)
    assert data["error_count"] == sum(issue["level"] == "ERROR" for issue in details)
    assert report.warn_count >= 3


@pytest.mark.parametrize("body", [[], ["无数字引用的正文。"], ["张三（2024）的工作。"]])
def test_unrecognized_body_is_explicitly_not_checked(tmp_path, body):
    report = analyze(_document(tmp_path / "论文.docx", body))
    assert not report.citations.checked
    assert report.citations.reason
    assert not report.citations.issues
    assert "正文引用核对：未完成" in build_text_report(report)
    assert "正文引用核对：未完成" in build_markdown_report(report)
    assert not json.loads(build_json_report(report))["citations"]["checked"]


@pytest.mark.parametrize("fmt", ["text", "md", "json"])
def test_cli_cross_check_warns_and_strict_fails(tmp_path, monkeypatch, capsys, fmt):
    monkeypatch.setattr(gui, "_supports_tk", lambda: False)
    path = _document(tmp_path / "引用缺失.docx", ["正文引用[1,4]。"])
    original = path.read_bytes()
    assert main([str(path), "--format", fmt]) == 0
    assert "S003" in capsys.readouterr().out
    assert main([str(path), "--format", fmt, "--strict"]) == 1
    assert "S004" in capsys.readouterr().out
    assert path.read_bytes() == original


def test_clean_citation_document_passes_strict_with_custom_section(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gui, "_supports_tk", lambda: False)
    path = _document(tmp_path / "clean.docx", ["结论依据[1-3]。再引用[2]。"], heading="References")
    assert main([str(path), "--section", "References", "--strict", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["citations"]["checked"]
    assert data["citations"]["issues"] == []
    assert data["warn_count"] == 0


def test_fullwidth_body_citations_pass_strict_and_preserve_reported_text(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(gui, "_supports_tk", lambda: False)
    path = _document(tmp_path / "全角引用.docx", ["依据[1]和［２－３］，年份［２０２４］。"])
    original = path.read_bytes()

    assert main([str(path), "--strict", "--format", "json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["citations"]["checked"]
    assert data["citations"]["issues"] == []
    assert [(item["raw"], item["numbers"]) for item in data["citations"]["citations"]] == [
        ("[1]", [1]),
        ("［２－３］", [2, 3]),
    ]
    assert path.read_bytes() == original


def test_missing_bibliography_does_not_claim_citation_check_completed(tmp_path):
    path = _document(tmp_path / "no-bib.docx", ["正文引用[1]。"], heading="其他章节")
    report = analyze(path)
    assert report.unavailable_reason
    assert not report.citations.checked
    assert not report.citations.issues
    assert not json.loads(build_json_report(report))["citations"]["checked"]


@pytest.mark.parametrize("layout", ["paragraphs", "manual_break", "table_columns"])
def test_fullwidth_reference_numbers_stay_separate_and_keep_citation_mapping(tmp_path, layout):
    entries = [
        "[1] 张三. 文一[J]. 学报, 2024.",
        "［２］ 李四. 文二[J]. 学报, 2023.",
    ]
    doc = Document()
    doc.add_paragraph("正文[1]［２］。")
    doc.add_heading("参考文献", level=1)
    if layout == "table_columns":
        table = doc.add_table(rows=1, cols=2)
        for cell, entry in zip(table.rows[0].cells, entries, strict=True):
            cell.text = entry
    elif layout == "manual_break":
        doc.add_paragraph("\n".join(entries))
    else:
        for entry in entries:
            doc.add_paragraph(entry)
    path = tmp_path / "fullwidth-numbers.docx"
    doc.save(path)
    original = path.read_bytes()

    report = analyze(path)

    assert [entry.text for entry in report.entries] == entries
    assert report.citations.checked
    assert report.citations.issues == []
    assert [(issue.level, issue.code) for issue in report.entries[1].issues] == [("ERROR", "E001")]
    fixed = fix_entries(entries, renumber=False)
    assert fixed["lines"] == [entries[0], "[２] 李四. 文二[J]. 学报, 2023."]
    assert not fixed["summary"]["renumbered"]
    assert fixed["summary"]["manual_needed"] == 0
    assert path.read_bytes() == original
