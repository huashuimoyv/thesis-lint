"""从 .docx 文档中定位并提取参考文献条目。

只处理普通段落文本；参考文献段以标题（如“参考文献”）开始，
到下一个同级/更高级 Heading 或常见后继章节（致谢、附录等）为止。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 常见的中断章节标题，匹配到即认为参考文献部分结束
_SECTION_STOP = re.compile(
    r"^(第?\s*\d+\s*章|致\s*谢|附\s*录|结\s*论|攻(读|士)|个人简历|创新点)",
)

_HEADING_HINT = re.compile(r"heading|标题", re.IGNORECASE)
_HEADING_LEVEL = re.compile(r"(?:heading|标题)\s*([1-9])", re.IGNORECASE)
_ENTRY_START = re.compile(r"^\[(\d+)\]\s*(.*)$")


@dataclass
class Bibliography:
    """一次提取的结果。"""

    found: bool = False
    heading_text: str = ""
    entries: list[str] = field(default_factory=list)
    # 条目序号与原文行号的对应关系（用于错误提示，1 起始）
    line_numbers: list[int] = field(default_factory=list)


def _is_heading(paragraph) -> bool:
    style = getattr(getattr(paragraph, "style", None), "name", "") or ""
    return bool(_HEADING_HINT.search(style))


def _heading_level(paragraph) -> int | None:
    style = getattr(getattr(paragraph, "style", None), "name", "") or ""
    match = _HEADING_LEVEL.search(style)
    return int(match.group(1)) if match else None


def _paragraph_text(paragraph) -> str:
    """合并段落内的手动换行与连续空白，避免正则只读取第一行。"""
    return " ".join((getattr(paragraph, "text", "") or "").split())


def _section_heading_pattern(section_keyword: str) -> re.Pattern[str] | None:
    keyword = section_keyword.strip()
    if not keyword:
        return None
    spaced_keyword = r"\s*".join(map(re.escape, keyword))
    number = r"(?:\d+(?:\.\d+)*|[一二三四五六七八九十百]+)"
    prefix = rf"(?:(?:第\s*)?{number}\s*(?:章)?\s*[.．、]?\s*)?"
    return re.compile(rf"^{prefix}{spaced_keyword}\s*[:：]?\s*$", re.IGNORECASE)


def find_bibliography(paragraphs, section_keyword: str = "参考文献") -> Bibliography:
    """扫描段落列表，返回参考文献部分。

    paragraphs: 任意可迭代的对象序列，需具备 ``.text`` 与可选 ``.style``。
    section_keyword: 章节标题关键词，允许中间夹杂空白字符。
    """
    result = Bibliography()
    paragraphs = list(paragraphs)
    keyword_re = _section_heading_pattern(section_keyword)
    if keyword_re is None:
        return result

    start = None
    section_level = None
    for i, p in enumerate(paragraphs):
        text = _paragraph_text(p)
        if not text:
            continue
        compact_length = len(re.sub(r"\s+", "", text))
        if keyword_re.fullmatch(text) and (_is_heading(p) or compact_length <= 10):
            start = i + 1
            section_level = _heading_level(p)
            result.found = True
            result.heading_text = text
            break

    if start is None:
        return result

    current: list[str] | None = None
    for i in range(start, len(paragraphs)):
        paragraph = paragraphs[i]
        raw = _paragraph_text(paragraph)
        if not raw:
            continue
        if _SECTION_STOP.match(raw):
            break
        if _is_heading(paragraph):
            level = _heading_level(paragraph)
            if section_level is not None and level is not None and level > section_level:
                continue
            break

        m = _ENTRY_START.match(raw)
        if m:
            if current is not None:
                result.entries.append(" ".join(current))
            # 保留完整原文（含序号），序号解析由 checker 负责
            current = [raw]
            result.line_numbers.append(i + 1)
        elif current is not None:
            # 不以 [n] 开头的行视为上一条目的折行，直接拼接
            current.append(raw)
        else:
            # 区内开头就是无序号正文：视为丢了序号的条目，交给 checker 报 E001，
            # 而不是静默跳过（否则"缺序号"这种错误用户永远看不到）
            current = [raw]
            result.line_numbers.append(i + 1)

    if current is not None:
        result.entries.append(" ".join(current))

    return result
