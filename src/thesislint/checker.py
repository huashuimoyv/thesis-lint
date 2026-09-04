"""GB/T 7714-2025 参考文献条目校验规则。

每条规则返回 Issue(level, code, message)：
- ERROR：确定不符合国标
- WARN ：疑似问题或建议（--strict 时同样视为失败）
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .patterns import (
    CITE_DATE_RE,
    FULLWIDTH_PUNCT,
    NUM_RE,
    TAG_RE,
    URL_RE,
    YEAR_RE,
    author_zone_bounds,
)

ERROR = "ERROR"
WARN = "WARN"

# 常用文献类型标识。带载体/OL 的组合形如 [J/OL]，单独放行。
_SINGLE_TAGS = {
    "J",
    "M",
    "C",
    "G",
    "N",
    "D",
    "R",
    "S",
    "P",
    "A",
    "DB",
    "DS",
    "CP",
    "MH",
    "CM",
    "EB",
}


@dataclass
class Issue:
    level: str
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.level}] {self.code}: {self.message}"


def check_entry(raw: str) -> list[Issue]:
    """校验单条参考文献条目，返回全部问题。"""
    issues: list[Issue] = []
    text = raw.strip()

    m = NUM_RE.match(text)
    if not m:
        issues.append(Issue(ERROR, "E001", "条目应以序号开头，如 “ [1] ”"))
        return issues
    body = m.group(2).strip()

    tag = None
    tag_m = TAG_RE.search(body)
    if not tag_m:
        issues.append(Issue(ERROR, "E002", "缺少文献类型标识，如 [J]、[M]、[D]、[C]、[EB/OL]"))
    else:
        tag = tag_m.group(1)
        base = tag.split("/")[0]
        if base not in _SINGLE_TAGS and tag not in _SINGLE_TAGS:
            issues.append(Issue(WARN, "W001", f"少见的文献类型标识 “[{tag}]”，请确认"))

    is_online = bool(tag) and "/OL" in tag
    if is_online:
        if not URL_RE.search(body):
            issues.append(Issue(ERROR, "E003", "电子资源（/OL）缺少获取路径（网址）"))
        if not CITE_DATE_RE.search(body):
            issues.append(Issue(WARN, "W002", "电子资源建议标注引用日期，如 [2025-01-01]"))

    if not YEAR_RE.search(body):
        issues.append(Issue(ERROR, "E004", "缺少出版年份（4 位数字）"))

    bounds = author_zone_bounds(text)
    zone = text[bounds[0] : bounds[1]] if bounds else ""
    # “等”与西文惯用的“et al.”均视为已正确缩略作者列表
    has_et_al = ", 等" in zone or "，等" in zone or "et al" in zone.lower()
    if not has_et_al and zone.count(",") + zone.count("，") >= 3:
        issues.append(
            Issue(
                WARN,
                "W003",
                "作者超过 3 人时应只列前 3 名，后加 “, 等”（GB/T 7714 第 8.1.2 条）",
            )
        )
    if re.search(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b", zone):
        issues.append(Issue(WARN, "W004", "西文作者应 “姓全大写 + 名首字母缩写”，如 “SMITH J A”"))

    if FULLWIDTH_PUNCT.search(body):
        issues.append(Issue(WARN, "W005", "条目内使用了全角标点（，。；：），国标要求半角"))

    if not text.endswith("."):
        issues.append(Issue(WARN, "W006", "条目未以句点“.”结尾"))

    return issues


def check_entries(entries: list[str]) -> tuple[list[list[Issue]], list[Issue]]:
    """批量校验。

    返回 (每条的 issue 列表, 段落级问题列表)。
    段落级问题包括序号跳号、重复等。
    """
    per_entry = [check_entry(e) for e in entries]
    section_issues: list[Issue] = []

    numbers: list[int] = []
    for raw in entries:
        m = NUM_RE.match(raw.strip())
        numbers.append(int(m.group(1)) if m else -1)

    seen: set[int] = set()
    for pos, n in enumerate(numbers, start=1):
        if n == -1:
            continue
        if n in seen:
            section_issues.append(Issue(ERROR, "S002", f"第 {pos} 条与前面的条目序号重复（{n}）"))
        seen.add(n)

    for pos in range(1, len(numbers)):
        prev_n, cur_n = numbers[pos - 1], numbers[pos]
        if cur_n != -1 and prev_n != -1 and cur_n != prev_n + 1:
            section_issues.append(
                Issue(WARN, "S001", f"第 {pos + 1} 条序号为 {cur_n}，但上一条为 {prev_n}，存在跳号")
            )

    return per_entry, section_issues
