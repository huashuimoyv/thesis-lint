"""使用临时合成文档验证指定便携程序的 CLI，不打开 GUI、不访问用户论文。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document


def _require(condition, scenario: str, detail: str) -> None:
    if not condition:
        raise RuntimeError(f"{scenario}: {detail}")


def _invoke(command: list[str], arguments: list[str], scenario: str, expected_exit: int):
    try:
        result = subprocess.run(
            [*command, *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{scenario}: process timed out after 30 seconds") from exc
    except OSError as exc:
        raise RuntimeError(f"{scenario}: executable could not start") from exc
    _require(
        result.returncode == expected_exit,
        scenario,
        f"expected exit {expected_exit}, got {result.returncode}",
    )
    return result


def _read_report(output: str, scenario: str) -> dict:
    try:
        report = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{scenario}: output is not valid JSON") from exc
    _require(isinstance(report, dict), scenario, "JSON report must be an object")
    return report


def verify_portable(command: list[str]) -> list[str]:
    """命令前缀仅供源码测试注入；公开脚本入口只接受一个明确的可执行文件。"""
    help_result = _invoke(command, ["--help"], "help", 0)
    _require(
        "--format" in help_result.stdout and "--strict" in help_result.stdout,
        "help",
        "CLI options are missing from help output",
    )
    completed = ["help"]
    with TemporaryDirectory(prefix="thesislint-portable-") as temporary:
        folder = Path(temporary)
        entries = [
            f"[{index}] 张三. 合成文献{index}[J]. 学报, 2024, 1(1): 1-9." for index in range(1, 4)
        ]
        table_path = folder / "中文 含空格的表格论文.docx"
        document = Document()
        document.add_paragraph("合成正文引用[1-3]。")
        document.add_heading("参考文献", level=1)
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "\n".join(entries[:2])
        table.cell(0, 1).text = entries[2]
        document.save(table_path)

        warning_path = folder / "只有 警告.docx"
        document = Document()
        document.add_paragraph("合成正文引用[1]。")
        document.add_heading("参考文献", level=1)
        document.add_paragraph(entries[0][:-1])
        document.save(warning_path)

        empty_path = folder / "空 参考文献.docx"
        document = Document()
        document.add_heading("参考文献", level=1)
        document.save(empty_path)
        corrupt_path = folder / "损坏 合成文档.docx"
        corrupt_path.write_bytes(b"synthetic invalid docx")
        originals = {
            path: path.read_bytes() for path in (table_path, warning_path, empty_path, corrupt_path)
        }

        for name, path, expected_entries, warning_count, numbers in (
            ("table", table_path, entries, 0, [1, 2, 3]),
            ("warning", warning_path, [entries[0][:-1]], 1, [1]),
        ):
            for strict in (False, True):
                scenario = f"{name} {'strict' if strict else 'normal'}"
                arguments = [str(path), "--format", "json", *(["--strict"] if strict else [])]
                result = _invoke(command, arguments, scenario, int(strict and warning_count > 0))
                report = _read_report(result.stdout, scenario)
                _require(report.get("source") == path.name, scenario, "wrong source filename")
                _require(report.get("found_section") is True, scenario, "bibliography not found")
                _require(report.get("unavailable_reason") is None, scenario, "check unavailable")
                _require(report.get("error_count") == 0, scenario, "unexpected errors")
                _require(report.get("warn_count") == warning_count, scenario, "wrong warning count")
                _require(report.get("section_issues") == [], scenario, "unexpected section issues")
                actual_entries = report.get("entries")
                _require(
                    isinstance(actual_entries, list)
                    and all(isinstance(entry, dict) for entry in actual_entries)
                    and [entry.get("text") for entry in actual_entries] == expected_entries,
                    scenario,
                    "entries differ from synthetic document",
                )
                expected_codes = [["W006"]] if warning_count else [[], [], []]
                _require(
                    [
                        [issue.get("code") for issue in entry.get("issues", [])]
                        for entry in actual_entries
                    ]
                    == expected_codes,
                    scenario,
                    "wrong entry issue codes",
                )
                citations = report.get("citations")
                _require(
                    isinstance(citations, dict)
                    and citations.get("checked") is True
                    and citations.get("has_body") is True
                    and citations.get("issues") == []
                    and [item.get("numbers") for item in citations.get("citations", [])]
                    == [numbers],
                    scenario,
                    "body citation check differs from synthetic document",
                )
                completed.append(scenario)

        scenario = "corrupt document"
        result = _invoke(command, [str(corrupt_path), "--format", "json"], scenario, 2)
        _require(
            not result.stdout.strip() and "无法解析文档" in result.stderr,
            scenario,
            "missing parse error or unexpected success report",
        )
        completed.append(scenario)

        scenario = "empty bibliography"
        result = _invoke(command, [str(empty_path), "--format", "json"], scenario, 2)
        report = _read_report(result.stdout, scenario)
        _require(
            report.get("source") == empty_path.name
            and report.get("found_section") is True
            and report.get("entries") == []
            and isinstance(report.get("unavailable_reason"), str)
            and bool(report["unavailable_reason"])
            and report.get("error_count") == 0
            and report.get("warn_count") == 0
            and isinstance(report.get("citations"), dict)
            and report["citations"].get("checked") is False,
            scenario,
            "empty bibliography must explicitly remain unchecked",
        )
        completed.append(scenario)
        _require(
            all(path.read_bytes() == content for path, content in originals.items()),
            "source preservation",
            "CLI changed a synthetic input document",
        )
    return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path, help="指定要验证的便携程序路径")
    args = parser.parse_args(argv)
    if not args.executable.is_file():
        parser.error("--executable must name an existing file")
    try:
        completed = verify_portable([str(args.executable.resolve())])
    except RuntimeError as exc:
        print(f"Portable CLI smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"Portable CLI smoke passed ({len(completed)} scenarios): {', '.join(completed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
