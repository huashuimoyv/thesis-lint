"""体检报告构建：text / markdown / json 三种格式。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class EntryResult:
    index: int  # 第几条（1 起始）
    line: int  # 文档中的行号
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

    @property
    def error_count(self) -> int:
        return sum(e.errors for e in self.entries) + sum(
            1 for i in self.section_issues if i.level == "ERROR"
        )

    @property
    def warn_count(self) -> int:
        return sum(e.warnings for e in self.entries) + sum(
            1 for i in self.section_issues if i.level == "WARN"
        )


def build_text_report(report: Report) -> str:
    lines: list[str] = []
    if not report.found_section:
        lines.append("未找到参考文献章节。请确认文档中有“参考文献”标题。")
        return "\n".join(lines)

    lines.append(f"{report.source} —— 参考文献共 {len(report.entries)} 条")
    lines.append("")

    for entry in report.entries:
        if not entry.issues:
            continue
        lines.append(
            f"[{entry.index}]（第 {entry.line} 行）{entry.text[:60]}{'…' if len(entry.text) > 60 else ''}"
        )
        for issue in entry.issues:
            mark = "[ERROR]" if issue.level == "ERROR" else "[WARN ]"
            lines.append(f"    {mark} {issue.code}: {issue.message}")
        lines.append("")

    for issue in report.section_issues:
        mark = "[ERROR]" if issue.level == "ERROR" else "[WARN ]"
        lines.append(f"{mark} {issue.code}: {issue.message}")

    n_pass = len(report.entries) - sum(1 for e in report.entries if e.issues)
    lines.append(
        f"体检结果：{n_pass} 条通过，{report.error_count} 个错误，{report.warn_count} 个警告"
    )
    return "\n".join(lines)


def build_markdown_report(report: Report) -> str:
    rows = ["| 条目 | 行号 | 级别 | 问题 |", "|---|---|---|---|"]
    for entry in report.entries:
        text = entry.text[:40].replace("|", "\\|")
        for issue in entry.issues:
            rows.append(
                f"| [{entry.index}] {text} | {entry.line} | {issue.level} | {issue.code} {issue.message} |"
            )
    # 章节级问题以独立行呈现，与 text / json 保持一致
    for issue in report.section_issues:
        rows.append(f"| **章节级** | — | {issue.level} | {issue.code} {issue.message} |")
    head = (
        f"# 参考文献体检报告：{report.source}\n\n"
        f"- 条目总数：{len(report.entries)}\n"
        f"- 错误：{report.error_count}\n"
        f"- 警告：{report.warn_count}\n"
    )
    return head + "\n".join(rows) + "\n"


def build_json_report(report: Report) -> str:
    data = {
        "source": report.source,
        "found_section": report.found_section,
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
    }
    return json.dumps(data, ensure_ascii=False, indent=2)
