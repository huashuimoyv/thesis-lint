"""命令行入口。

用法：
    thesislint 论文.docx                  # 文本报告
    thesislint 论文.docx --format md      # Markdown 报告
    thesislint 论文.docx --strict         # 警告也视为失败（CI 用）
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from docx import Document

from .checker import ERROR, check_entries
from .extractor import find_bibliography
from .report import EntryResult, Report, build_json_report, build_markdown_report, build_text_report


def analyze(path: Path, section_keyword: str = "参考文献") -> Report:
    doc = Document(str(path))
    bib = find_bibliography(doc.paragraphs, section_keyword)
    per_entry, section_issues = check_entries(bib.entries) if bib.found else ([], [])

    report = Report(source=path.name, found_section=bib.found, section_issues=section_issues)
    for i, text in enumerate(bib.entries):
        report.entries.append(
            EntryResult(
                index=i + 1,
                line=bib.line_numbers[i] if i < len(bib.line_numbers) else 0,
                text=text,
                issues=per_entry[i],
            )
        )
    return report


def _force_utf8_stdio() -> None:
    """Windows 控制台重定向输出时默认 GBK，遇到中文/特殊字符会崩溃。

    统一切到 UTF-8（老终端无法显示的字符降级替换而不是报错）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            # 刻意宽捕获：任一失败都走降级路径
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    # argparse 的 --help 与用法错误会在 parse_args 内直接输出，必须在建 parser 前设置编码。
    _force_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="thesislint",
        description="毕业论文「国标体检」：检查 Word 文档参考文献是否符合 GB/T 7714-2025",
    )
    parser.add_argument("docx", type=Path, nargs="?", help="待检查的 .docx 文件")
    parser.add_argument("--section", default="参考文献", help="章节标题关键词（默认“参考文献”）")
    parser.add_argument("--format", choices=["text", "md", "json"], default="text", help="输出格式")
    parser.add_argument("--strict", action="store_true", help="存在警告时同样返回非零退出码")

    raw = list(sys.argv[1:]) if argv is None else list(argv)

    # 双模式分发：直接双击 exe（无参数）或从资源管理器拖文件到图标上时，
    # 打开图形界面；真正的命令行调用行为完全不变。
    if not any(a.startswith("-") for a in raw):
        from .gui import should_launch_gui

        if should_launch_gui(raw):
            from .gui import run_gui

            return run_gui(Path(raw[0]) if raw else None)

    args = parser.parse_args(raw)

    if args.docx is None:
        parser.print_help()
        return 2

    if args.docx.suffix.lower() != ".docx":
        print(
            f"暂只支持 .docx，收到的是 {args.docx.suffix}。请先用 Word 另存为 .docx。",
            file=sys.stderr,
        )
        return 2
    if not args.docx.exists():
        print(f"文件不存在：{args.docx}", file=sys.stderr)
        return 2

    try:
        report = analyze(args.docx, args.section)
    except Exception as exc:  # 损坏的文档等  # noqa: BLE001  刻意宽捕获：任一失败都走降级路径
        print(f"无法解析文档：{exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(build_json_report(report))
    elif args.format == "md":
        print(build_markdown_report(report))
    else:
        print(build_text_report(report))

    if report.unavailable_reason:
        return 2
    has_error = any(i.level == ERROR for i in report.section_issues) or report.error_count > 0
    return 1 if (has_error or (args.strict and report.warn_count > 0)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
