"""参考文献轻量字段解析。

解析结果只服务于保守校验。无法可靠识别的字段保持为空，避免把解析失败
误报成格式错误。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .patterns import NUM_RE, TAG_RE, URL_RE, YEAR_RE

DOI_HINT_RE = re.compile(r"(?i)(?:\bdoi\s*:|https?://doi\.org/|\b10\.\d{2,9}/)")
DOI_RE = re.compile(r"(?i)\b10\.\d{4,9}/[-._;()/:A-Z0-9]+")
PAGE_RANGE_RE = re.compile(r":\s*([A-Za-z]?\d+)\s*([-~～–—])\s*([A-Za-z]?\d+)(?=\s*[.,;)]|\s*$)")
PUBLICATION_RE = re.compile(r"(?:^|[.]\s*)([^,.;:]{1,40})\s*:\s*([^,.;]{1,80})\s*,\s*$")


@dataclass(frozen=True)
class ReferenceFields:
    number: int | None
    body: str
    tag: str | None
    base_tag: str | None
    years: tuple[str, ...]
    url: str | None
    doi: str | None
    doi_hint: bool
    page_range: tuple[int, int] | None
    page_separator: str | None
    publication_place: str | None
    publisher: str | None


def parse_reference(raw: str) -> ReferenceFields:
    """尽力解析单条参考文献；字段不确定时返回 ``None``。"""
    text = raw.strip()
    number_match = NUM_RE.match(text)
    number = int(number_match.group(1)) if number_match else None
    body = number_match.group(2).strip() if number_match else text

    tag_match = TAG_RE.search(body)
    tag = tag_match.group(1) if tag_match else None
    base_tag = tag.split("/", 1)[0] if tag else None
    years = tuple(YEAR_RE.findall(body))

    url_match = URL_RE.search(body)
    url = body[url_match.start() :].split()[0].rstrip(".,;。；") if url_match else None

    doi_match = DOI_RE.search(body)
    doi = doi_match.group(0).rstrip(".,;") if doi_match else None

    page_match = None
    for candidate in PAGE_RANGE_RE.finditer(body):
        page_match = candidate
    page_range = None
    page_separator = None
    if page_match:
        start, separator, end = page_match.groups()
        page_separator = separator
        if start.isdigit() and end.isdigit():
            page_range = (int(start), int(end))

    publication_place = None
    publisher = None
    if tag_match:
        after_tag = body[tag_match.end() :]
        year_match = YEAR_RE.search(after_tag)
        before_year = after_tag[: year_match.start()] if year_match else after_tag
        publication_match = PUBLICATION_RE.search(before_year)
        if publication_match:
            publication_place, publisher = (value.strip() for value in publication_match.groups())

    return ReferenceFields(
        number=number,
        body=body,
        tag=tag,
        base_tag=base_tag,
        years=years,
        url=url,
        doi=doi,
        doi_hint=bool(DOI_HINT_RE.search(body)),
        page_range=page_range,
        page_separator=page_separator,
        publication_place=publication_place,
        publisher=publisher,
    )
