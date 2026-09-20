"""从 .docx 文档中定位并提取参考文献条目。

按正文顺序处理普通段落与表格行；参考文献段以标题（如“参考文献”）开始，
到下一个同级/更高级 Heading 或常见后继章节（致谢、附录等）为止。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import SimpleNamespace

from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl, CT_Tc
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

# 常见的中断章节标题，匹配到即认为参考文献部分结束
_SECTION_STOP = re.compile(
    r"^(第?\s*\d+\s*章|致\s*谢|附\s*录|结\s*论|攻(读|士)|个人简历|创新点)",
)

_HEADING_HINT = re.compile(r"heading|标题", re.IGNORECASE)
_HEADING_LEVEL = re.compile(r"(?:heading|标题)\s*([1-9])", re.IGNORECASE)
_ENTRY_START = re.compile(r"^\[(\d+)\]\s*(.*)$")
_ENTRY_BREAK = re.compile(r"[\r\n]+(?=[^\S\r\n]*\[\d+\])")
_TABLE_HEADER = re.compile(r"^(?:序号|编号)\s*(?:参考文献|文献(?:名称|条目)?)$")
_TEXT_CONTAINERS = {qn(tag) for tag in ("w:r", "w:hyperlink", "w:fldSimple")}
_TEXT_ELEMENTS = {qn(tag) for tag in ("w:t", "w:tab", "w:ptab", "w:br", "w:cr", "w:noBreakHyphen")}


def _paragraph_block(paragraph, fields: list[bool]):
    """读取已有的域显示结果，不执行域指令，也不深入文本框等非正文区域。"""
    if not isinstance(paragraph, Paragraph):
        return paragraph
    parts: list[str] = []

    def read(element):
        for child in element:
            if child.tag == qn("w:fldChar"):
                kind = child.get(qn("w:fldCharType"))
                if kind == "begin":
                    fields.append(False)
                elif kind == "separate" and fields:
                    fields[-1] = True
                elif kind == "end" and fields:
                    fields.pop()
            elif child.tag in _TEXT_CONTAINERS:
                read(child)
            elif child.tag in _TEXT_ELEMENTS and all(fields):
                parts.append(str(child))

    read(paragraph._p)
    return SimpleNamespace(text="".join(parts), style=paragraph.style)


@dataclass
class Bibliography:
    """一次提取的结果。"""

    found: bool = False
    heading_text: str = ""
    entries: list[str] = field(default_factory=list)
    # 条目与文档块位置的对应关系（段落或表格行，1 起始）
    line_numbers: list[int] = field(default_factory=list)
    # 文献标题之前的文档块文本，保留空块以维持位置对应。
    body_paragraphs: list[str] = field(default_factory=list)


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


def _is_section_heading(paragraph, keyword_re: re.Pattern[str] | None) -> bool:
    text = _paragraph_text(paragraph)
    return bool(
        keyword_re is not None
        and keyword_re.fullmatch(text)
        and (_is_heading(paragraph) or len(re.sub(r"\s+", "", text)) <= 10)
    )


def _is_section_end(paragraph, section_level: int | None) -> bool:
    text = _paragraph_text(paragraph)
    if not text:
        return False
    if _SECTION_STOP.match(text):
        return True
    if not _is_heading(paragraph):
        return False
    level = _heading_level(paragraph)
    return not (section_level is not None and level is not None and level > section_level)


def find_bibliography(paragraphs, section_keyword: str = "参考文献") -> Bibliography:
    """扫描段落列表，返回参考文献部分。

    paragraphs: 任意可迭代的对象序列，需具备 ``.text`` 与可选 ``.style``。
    section_keyword: 章节标题关键词，允许中间夹杂空白字符。
    """
    result = Bibliography()
    fields: list[bool] = []
    paragraphs = [_paragraph_block(paragraph, fields) for paragraph in paragraphs]
    result.body_paragraphs = [_paragraph_text(p) for p in paragraphs]
    keyword_re = _section_heading_pattern(section_keyword)
    if keyword_re is None:
        return result

    start = None
    section_level = None
    for i, p in enumerate(paragraphs):
        text = _paragraph_text(p)
        if not text:
            continue
        if _is_section_heading(p, keyword_re):
            start = i + 1
            section_level = _heading_level(p)
            result.found = True
            result.heading_text = text
            result.body_paragraphs = result.body_paragraphs[:i]
            break

    if start is None:
        return result

    current: list[str] | None = None
    for i in range(start, len(paragraphs)):
        paragraph = paragraphs[i]
        raw = _paragraph_text(paragraph)
        if not raw:
            continue
        if _is_section_end(paragraph, section_level):
            break
        if _is_heading(paragraph):
            continue

        # 先按“换行 + 新序号”分条，再合并普通折行；同一段中的条目共享段落号。
        for fragment in _ENTRY_BREAK.split(paragraph.text or ""):
            entry_text = " ".join(fragment.split())
            if not entry_text:
                continue
            if _ENTRY_START.match(entry_text):
                if current is not None:
                    result.entries.append(" ".join(current))
                current = [entry_text]
                result.line_numbers.append(i + 1)
            elif current is not None:
                current.append(entry_text)
            else:
                # 缺号条目也保留，交给 checker 报 E001。
                current = [entry_text]
                result.line_numbers.append(i + 1)

    if current is not None:
        result.entries.append(" ".join(current))

    return result


def _iter_document_blocks(document, section_keyword: str = "参考文献"):
    """按 Word 正文顺序产出段落和表格行。"""
    keyword_re = _section_heading_pattern(section_keyword)
    in_bibliography = False
    section_level = None
    fields: list[bool] = []
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = _paragraph_block(Paragraph(child, document), fields)
            if _is_section_heading(paragraph, keyword_re):
                in_bibliography = True
                section_level = _heading_level(paragraph)
            elif in_bibliography and _is_section_end(paragraph, section_level):
                in_bibliography = False
            yield paragraph
        elif isinstance(child, CT_Tbl):
            table = Table(child, document)
            # 合并单元格在多行/多列映射到同一 XML 节点；保留节点引用而非文本去重。
            seen_cells: set[CT_Tc] = set()
            for row in table.rows:
                parts: list[str] = []
                for cell in row.cells:
                    if cell._tc in seen_cells:
                        continue
                    seen_cells.add(cell._tc)
                    # 表格仍位于正文顺序中，域的开始/分隔/结束状态须跨单元格传播。
                    cell_text = "\n".join(
                        _paragraph_block(paragraph, fields).text for paragraph in cell.paragraphs
                    ).strip()
                    if cell_text:
                        parts.append(cell_text)
                row_block = SimpleNamespace(text=" ".join(parts), style=SimpleNamespace(name=""))
                if _is_section_heading(row_block, keyword_re):
                    in_bibliography = True
                    section_level = None
                elif in_bibliography and _is_section_end(row_block, section_level):
                    in_bibliography = False
                if not in_bibliography:
                    # 正文行完整保留，避免把开头带引用的单元格误当成文献条目。
                    yield row_block
                    continue
                # 只在判断开头时合并空白；输出保留格内换行，供后续逐条拆分。
                entry_cells = [part for part in parts if _ENTRY_START.match(" ".join(part.split()))]
                row_texts = entry_cells if len(entry_cells) > 1 else [" ".join(parts)]
                for row_text in row_texts:
                    if _TABLE_HEADER.fullmatch(" ".join(row_text.split())):
                        continue
                    yield SimpleNamespace(
                        text=row_text,
                        style=SimpleNamespace(name=""),
                    )


def find_bibliography_in_document(document, section_keyword: str = "参考文献") -> Bibliography:
    """从 ``python-docx`` 文档正文和表格中提取参考文献。"""
    return find_bibliography(_iter_document_blocks(document, section_keyword), section_keyword)
