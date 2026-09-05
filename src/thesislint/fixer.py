"""参考文献条目自动修正引擎。

设计原则：
- 只做**确定性**变换（标点规范化、补句点、作者截断加等、重新编号），
  改错了比不改更糟；不确定的一律放进 unresolved 让用户手工处理。
- 修正后重新过一遍 checker，把仍然存在的警告如实返回（remaining）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .checker import check_entry
from .parser import PAGE_RANGE_RE, parse_reference
from .patterns import (
    CITE_DATE_RE,
    FULLWIDTH_TRANS,
    NUM_RE,
    TAG_RE,
    URL_RE,
    YEAR_RE,
    author_zone_bounds,
)

# 用于截断作者：至少要有 [类型标识] 才能可靠界定作者区
_AUTHOR_SPLIT_RE = re.compile(r"\s*,\s*")


@dataclass
class EntryFix:
    index: int  # 修正后列表中的序号（1 起始）
    original: str
    fixed: str
    fixes: list[str] = field(default_factory=list)  # 已自动应用的修正说明
    unresolved: list[str] = field(default_factory=list)  # 需人工处理的原因
    remaining_warnings: int = 0  # 修正后仍剩余的警告数


def fix_entry(text: str, new_index: int) -> EntryFix:
    original = text.strip()
    work = original
    fixes: list[str] = []
    unresolved: list[str] = []

    # 1. 序号：缺号或错号都按新序号重排
    num_m = NUM_RE.match(work)
    if not num_m:
        work = f"[{new_index}] {work}"
        fixes.append("补齐条目序号")
    else:
        body = num_m.group(2)
        work = f"[{new_index}] {body}"
        if num_m.group(1) != str(new_index):
            fixes.append("重新编号")

    # 2. 全角标点 → 半角
    translated = work.translate(FULLWIDTH_TRANS)
    if translated != work:
        work = translated
        fixes.append("全角标点改为半角")

    def normalize_page_separator(match: re.Match[str]) -> str:
        start, separator, end = match.groups()
        return f": {start}-{end}" if separator != "-" else match.group(0)

    normalized_pages = PAGE_RANGE_RE.sub(normalize_page_separator, work)
    if normalized_pages != work:
        work = normalized_pages
        fixes.append("页码区间分隔符改为半角连字符")

    # 3. 尾部句点
    if not work.endswith("."):
        work = work.rstrip() + "."
        fixes.append("补尾部句点")
    work = re.sub(r"\s{2,}", " ", work)

    # 4. 作者区修整：仅当类型标识存在时才可靠
    bounds = author_zone_bounds(work)
    if bounds:
        zone = work[bounds[0] : bounds[1]]
        has_et_al = ("等" in zone) or ("et al" in zone.lower())
        if not has_et_al:
            parts = [p.strip() for p in _AUTHOR_SPLIT_RE.split(zone) if p.strip()]
            # 作者区已由“作者. 题名”分隔符限定；每段仍须像短作者名才自动修改。
            if len(parts) >= 4 and all(len(p) <= 40 for p in parts):
                new_zone = ", ".join(parts[:3]) + ", 等"
                work = work[: bounds[0]] + new_zone + work[bounds[1] :]
                fixes.append("作者超过 3 人，截断为前 3 名并加 “, 等”")

    # 5. 检查无法自动解决的问题（与 checker 的 ERROR 对应）
    tag_match = TAG_RE.search(work)
    if not tag_match:
        unresolved.append("缺少文献类型标识（[J]/[M]/[D]/[C]/[EB/OL]…），无法自动判断文献类型")
    if not YEAR_RE.search(work):
        unresolved.append("缺少出版年份，请自行补充")
    if tag_match and "/OL" in tag_match.group(1):
        if not URL_RE.search(work):
            unresolved.append("电子资源缺少获取路径（网址）")
        if not CITE_DATE_RE.search(work):
            unresolved.append("电子资源建议补充引用日期 [YYYY-MM-DD]")

    fields = parse_reference(work)
    if fields.page_range and fields.page_range[0] > fields.page_range[1]:
        unresolved.append("页码区间起止页疑似颠倒，请核对")
    if fields.doi_hint and not fields.doi:
        unresolved.append("DOI 格式疑似不完整，请核对")
    if (
        fields.base_tag == "M"
        and (not fields.tag or "/OL" not in fields.tag)
        and not (fields.publication_place and fields.publisher)
    ):
        unresolved.append("纸质专著缺少可识别的出版地或出版者，请补充")

    # 6. 修正后剩余的警告（如西文姓名未缩写等），如实提示
    remaining = [i for i in check_entry(work) if i.level == "WARN"]

    return EntryFix(
        index=new_index,
        original=original,
        fixed=work,
        fixes=fixes,
        unresolved=unresolved,
        remaining_warnings=len(remaining),
    )


def fix_entries(entries: list[str]) -> dict:
    """批量修正，返回供 UI / 报告使用的结构化结果。"""
    results = [fix_entry(e, i + 1) for i, e in enumerate(entries)]
    auto_fixed = sum(1 for r in results if r.fixes)
    manual = [r for r in results if r.unresolved]
    renumbered = any("重新编号" in f or "补齐条目序号" in f for r in results for f in r.fixes)
    return {
        "results": results,
        "lines": [r.fixed for r in results],
        "summary": {
            "total": len(results),
            "auto_fixed": auto_fixed,
            "untouched": len(results) - auto_fixed,
            "manual_needed": len(manual),
            "renumbered": renumbered,
        },
    }
