"""报告层测试：三种格式必须信息对等。

背景：v0.4.0 的 build_json_report / build_markdown_report 均漏掉了
section_issues，导致"报告说有 1 个错误，明细里却找不到"。
本文件的 TestFormatParity 就是防止这类信息丢失回归的总闸。
"""

from __future__ import annotations

import json
import re

from thesislint.checker import check_entries
from thesislint.report import (
    EntryResult,
    Report,
    build_json_report,
    build_markdown_report,
    build_text_report,
)

_CODE_RE = re.compile(r"[EW]\d{3}|S\d{3}")


def _sample_report() -> Report:
    """构造一个同时含条目级与章节级问题的报告。"""
    entries = [
        "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
        "[1] 李四. 文二[J]. 学报, 2024, 2(1): 1-9.",  # 序号重复 -> S002
        "[5] 王五. 文三[J]. 学报, 2024, 3(1): 1-9.",  # 序号跳号 -> S001
    ]
    per_entry, section_issues = check_entries(entries)
    r = Report(source="t.docx", found_section=True, section_issues=section_issues)
    for i, (text, issues) in enumerate(zip(entries, per_entry, strict=True)):
        r.entries.append(EntryResult(index=i + 1, line=i + 1, text=text, issues=issues))
    return r


class TestSectionIssuesPresentInAllFormats:
    """章节级问题必须在三种输出格式里都能被找到。"""

    def test_text_has_section_issues(self):
        assert "S002" in build_text_report(_sample_report())

    def test_markdown_has_section_issues(self):
        assert "S002" in build_markdown_report(_sample_report())

    def test_json_has_section_issues(self):
        data = json.loads(build_json_report(_sample_report()))
        codes = [i["code"] for i in data["section_issues"]]
        assert "S002" in codes
        assert "S001" in codes


class TestFormatParity:
    """三种格式的 issue code 集合必须完全一致（防信息丢失的总闸）。"""

    def test_same_codes_across_formats(self):
        r = _sample_report()
        codes_text = set(_CODE_RE.findall(build_text_report(r)))
        codes_md = set(_CODE_RE.findall(build_markdown_report(r)))
        data = json.loads(build_json_report(r))
        codes_json = {i["code"] for e in data["entries"] for i in e["issues"]}
        codes_json |= {i["code"] for i in data["section_issues"]}

        assert codes_text, "样本本身应含 issue，否则空集合相等会假通过"
        assert codes_text == codes_md == codes_json


class TestCountersMatchDetails:
    """计数器与明细必须对得上账。"""

    def test_json_counts_are_locatable(self):
        data = json.loads(build_json_report(_sample_report()))
        detail_errors = sum(
            1 for e in data["entries"] for i in e["issues"] if i["level"] == "ERROR"
        ) + sum(1 for i in data["section_issues"] if i["level"] == "ERROR")
        detail_warns = sum(
            1 for e in data["entries"] for i in e["issues"] if i["level"] == "WARN"
        ) + sum(1 for i in data["section_issues"] if i["level"] == "WARN")

        assert data["error_count"] == detail_errors
        assert data["warn_count"] == detail_warns


class TestEdgeCases:
    def test_not_found_section(self):
        r = Report(source="x.docx", found_section=False)
        assert "未找到参考文献章节" in build_text_report(r)
        assert "未找到参考文献章节" in build_markdown_report(r)
        assert '"found_section": false' in build_json_report(r)

    def test_empty_report(self):
        r = Report(source="x.docx", found_section=True)
        assert "未提取到" in build_text_report(r)
        assert "未提取到" in build_markdown_report(r)
        assert "0 条通过" not in build_text_report(r)
        data = json.loads(build_json_report(r))
        assert data["entries"] == []
        assert "未提取到" in data["unavailable_reason"]

    def test_checkable_report_has_no_unavailable_reason(self):
        assert json.loads(build_json_report(_sample_report()))["unavailable_reason"] is None
