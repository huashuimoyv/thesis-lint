"""体检报告构建：text / markdown / json 三种格式。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from html import escape

from .citations import CitationCheck


@dataclass
class EntryResult:
    index: int  # 第几条（1 起始）
    line: int  # 文档块序号（段落或表格行，1 起始）；兼容既有 JSON 字段名
    text: str
    issues: list  # list[checker.Issue]

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.level == "ERROR")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.level == "WARN")


@dataclass
class Report:
    source: str = ""
    found_section: bool = False
    entries: list[EntryResult] = field(default_factory=list)
    section_issues: list = field(default_factory=list)
    citations: CitationCheck | None = None

    @property
    def unavailable_reason(self) -> str | None:
        """未完成检查的原因；不把提取失败算作文献格式错误。"""
        if not self.found_section:
            return "未完成检查：未找到参考文献章节。请确认章节标题与检查关键词一致。"
        if not self.entries:
            return (
                "未完成检查：已找到参考文献章节，但未提取到可检查的条目。"
                "请确认参考文献位于章节标题后的正文或表格中；图片中的文字暂不支持。"
            )
        return None

    @property
    def error_count(self) -> int:
        return (
            sum(e.errors for e in self.entries)
            + sum(1 for i in self.section_issues if i.level == "ERROR")
            + sum(
                1 for i in (self.citations.issues if self.citations else []) if i.level == "ERROR"
            )
        )

    @property
    def warn_count(self) -> int:
        return (
            sum(e.warnings for e in self.entries)
            + sum(1 for i in self.section_issues if i.level == "WARN")
            + sum(1 for i in (self.citations.issues if self.citations else []) if i.level == "WARN")
        )


def _citation_summary(check: CitationCheck) -> str:
    if not check.checked:
        return f"正文引用核对：未完成（{check.reason or '缺少可核对的数据'}）"
    numbers = {number for citation in check.citations for number in citation.numbers}
    return (
        f"正文引用核对：识别到 {len(check.citations)} 处引用标记，涉及 {len(numbers)} 个编号。"
        "仅核对参考文献章节之前正文及表格中的数字方括号引用；"
        "脚注、尾注、文本框和图片未纳入核对，疑似问题请人工确认。"
    )


def build_text_report(report: Report, level: str | None = None) -> str:
    """构建文本报告；``level`` 可只显示 ERROR 或 WARN 明细。"""
    if level not in (None, "ERROR", "WARN"):
        raise ValueError("level must be None, 'ERROR', or 'WARN'")
    lines: list[str] = []
    if report.unavailable_reason:
        return report.unavailable_reason

    lines.append(f"{report.source} —— 参考文献共 {len(report.entries)} 条")
    lines.append("")

    for entry in report.entries:
        visible_issues = [issue for issue in entry.issues if level is None or issue.level == level]
        if not visible_issues:
            continue
        lines.append(
            f"[{entry.index}]（文档块 {entry.line}）{entry.text[:60]}{'…' if len(entry.text) > 60 else ''}"
        )
        for issue in visible_issues:
            mark = "[ERROR]" if issue.level == "ERROR" else "[WARN ]"
            lines.append(f"    {mark} {issue.code}: {issue.message}")
        lines.append("")

    for issue in report.section_issues:
        if level is not None and issue.level != level:
            continue
        mark = "[ERROR]" if issue.level == "ERROR" else "[WARN ]"
        lines.append(f"{mark} {issue.code}: {issue.message}")

    if report.citations is not None:
        lines.extend(["", _citation_summary(report.citations)])
        for issue in report.citations.issues:
            if level is None or issue.level == level:
                mark = "[ERROR]" if issue.level == "ERROR" else "[WARN ]"
                lines.append(f"{mark} {issue.code}: {issue.message}")
        lines.append("")

    n_pass = len(report.entries) - sum(1 for e in report.entries if e.issues)
    lines.append(
        f"体检结果：{n_pass} 条通过，{report.error_count} 个错误，{report.warn_count} 个警告"
    )
    return "\n".join(lines)


def _markdown_cell(text: str) -> str:
    """以字面文字显示动态内容，换行仍保留在同一 Markdown 块内。"""
    literal = re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", escape(text, quote=False))
    return literal.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def build_markdown_report(report: Report) -> str:
    source = _markdown_cell(report.source)
    if report.unavailable_reason:
        return f"# 参考文献体检报告：{source}\n\n{report.unavailable_reason}\n"

    rows = ["| 条目 | 文档块 | 级别 | 问题 |", "|---|---|---|---|"]
    for entry in report.entries:
        text = _markdown_cell(entry.text[:40])
        for issue in entry.issues:
            rows.append(
                f"| [{entry.index}] {text} | {entry.line} | {issue.level} | {issue.code} {_markdown_cell(issue.message)} |"
            )
    # 章节级问题以独立行呈现，与 text / json 保持一致
    for issue in report.section_issues:
        rows.append(
            f"| **章节级** | — | {issue.level} | {issue.code} {_markdown_cell(issue.message)} |"
        )
    head = (
        f"# 参考文献体检报告：{source}\n\n"
        f"- 条目总数：{len(report.entries)}\n"
        f"- 错误：{report.error_count}\n"
        f"- 警告：{report.warn_count}\n"
    )
    result = head + "\n" + "\n".join(rows) + "\n"
    if report.citations is not None:
        result += f"\n## 正文引用核对\n\n{_markdown_cell(_citation_summary(report.citations))}\n"
        for issue in report.citations.issues:
            result += f"\n- {issue.level} {issue.code}: {_markdown_cell(issue.message)}\n"
    return result


def build_json_report(report: Report) -> str:
    data = {
        "source": report.source,
        "found_section": report.found_section,
        "unavailable_reason": report.unavailable_reason,
        "error_count": report.error_count,
        "warn_count": report.warn_count,
        "entries": [
            {
                **asdict(e),
                "issues": [asdict(i) for i in e.issues],
            }
            for e in report.entries
        ],
        # 章节级问题必须可寻址，否则 error_count 无法与明细对账
        "section_issues": [asdict(i) for i in report.section_issues],
        "citations": asdict(report.citations) if report.citations is not None else None,
    }
    return json.dumps(data, ensure_ascii=False, indent=2)
