"""正文顺序编码引用与参考文献表的保守交叉核对。

仅识别方括号内 1–999 的编号及其组合；四位年份、日期、倒序范围等
不作为引用。位置沿用 extractor 的文档块序号，并非 Word 的物理行号。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .checker import WARN, Issue
from .extractor import Bibliography
from .patterns import NUM_RE

_BRACKETS = re.compile(r"(?<![\[［])(?:\[([^\[\]［］]*)\]|［([^\[\]［］]*)］)(?![\]］])")
_NUMBER = r"[1-9][0-9]{0,2}"
_DASH = r"[-‐‑–—−－~～至]"
_ITEM = rf"{_NUMBER}(?:\s*{_DASH}\s*{_NUMBER})?"
_GROUP = re.compile(rf"\s*{_ITEM}(?:\s*[,，、]\s*{_ITEM})*\s*")
_SPLIT_ITEMS = re.compile(r"\s*[,，、]\s*")
_SPLIT_RANGE = re.compile(rf"\s*{_DASH}\s*")


@dataclass
class Citation:
    numbers: list[int]
    line: int
    raw: str


@dataclass
class CitationCheck:
    checked: bool = False
    reason: str | None = None
    citations: list[Citation] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    has_body: bool = False


def _find_citations(body_paragraphs: list[str]) -> list[Citation]:
    citations: list[Citation] = []
    for line, text in enumerate(body_paragraphs, start=1):
        for match in _BRACKETS.finditer(text):
            content = match.group(1) if match.group(1) is not None else match.group(2)
            if len(content) > 2000 or not _GROUP.fullmatch(content):
                continue
            numbers: list[int] = []
            for item in _SPLIT_ITEMS.split(content.strip()):
                bounds = [int(value) for value in _SPLIT_RANGE.split(item)]
                start, end = bounds[0], bounds[-1]
                if end < start:
                    break
                numbers.extend(range(start, end + 1))
            else:
                citations.append(Citation(numbers, line, match.group(0)))
    return citations


def check_citations(bib: Bibliography) -> CitationCheck:
    """核对可识别的正文引用；映射不可靠或没有引用时说明原因并跳过。

    S003：正文编号没有对应条目；S004：条目没有可识别的正文引用；
    S005：首次引用未从 1 开始，或新的编号小于此前首次引用的编号。
    所有问题均为人工核对提示，不自动修改正文或参考文献编号。
    """
    result = CitationCheck(has_body=any(text.strip() for text in bib.body_paragraphs))
    if not bib.found:
        result.reason = "未找到参考文献章节，无法核对正文引用。"
        return result
    # 比较无法执行时也保留识别结果，供调用方判断正文是否已有引用。
    result.citations = _find_citations(bib.body_paragraphs)
    if not bib.entries:
        result.reason = "参考文献章节为空，无法核对正文引用。"
        return result

    numbers: list[int] = []
    for entry in bib.entries:
        match = NUM_RE.match(entry.strip())
        if match is None or len(match.group(1)) > 3:
            result.reason = "参考文献编号缺失或超出可识别范围（1–999），无法可靠映射正文引用。"
            return result
        number = int(match.group(1))
        if number < 1 or number in numbers:
            result.reason = "参考文献编号含非正数或重复编号，无法可靠映射正文引用。"
            return result
        numbers.append(number)

    if not result.has_body:
        result.reason = "参考文献标题前没有正文文本，未执行引用核对。"
        return result
    if not result.citations:
        result.reason = "未识别到正文方括号数字引用（支持 1–999 的编号及其组合），未执行引用核对。"
        return result
    result.checked = True

    available = set(numbers)
    seen: set[int] = set()
    last_first: int | None = None
    for citation in result.citations:
        for number in citation.numbers:
            if number in seen:
                continue
            seen.add(number)
            if number not in available:
                result.issues.append(
                    Issue(
                        WARN,
                        "S003",
                        f"文档块 {citation.line} 的正文引用 [{number}] 在参考文献表中没有对应条目。",
                    )
                )
                continue
            if last_first is None and number != 1:
                result.issues.append(
                    Issue(
                        WARN,
                        "S005",
                        f"文档块 {citation.line} 首次引用的文献编号为 [{number}]，顺序编码建议从 [1] 开始。",
                    )
                )
            elif last_first is not None and number < last_first:
                result.issues.append(
                    Issue(
                        WARN,
                        "S005",
                        f"文档块 {citation.line} 的 [{number}] 首次出现于 [{last_first}] 之后，请核对首次引用顺序。",
                    )
                )
            last_first = number

    for index, number in enumerate(numbers):
        if number not in seen:
            location = (
                f"（文档块 {bib.line_numbers[index]}）" if index < len(bib.line_numbers) else ""
            )
            result.issues.append(
                Issue(
                    WARN,
                    "S004",
                    f"参考文献 [{number}]{location} 未在可识别的正文引用中出现，请人工核对。",
                )
            )
    return result
