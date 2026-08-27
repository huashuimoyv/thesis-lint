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

_FULLWIDTH_TRANS = str.maketrans({
    "，": ", ", "。": ".", "；": "; ", "：": ": ",
    "（": "(", "）": ")", "？": "?", "！": "!",
})

_TAG_RE = re.compile(r"\[([A-Z]{1,2}(?:/[A-Z]{1,2})?)\]")
_NUM_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")
# 用于截断作者：至少要有 [类型标识] 才能可靠界定作者区
_AUTHOR_SPLIT_RE = re.compile(r"\s*,\s*")


@dataclass
class EntryFix:
    index: int                 # 修正后列表中的序号（1 起始）
    original: str
    fixed: str
    fixes: list[str] = field(default_factory=list)      # 已自动应用的修正说明
    unresolved: list[str] = field(default_factory=list)  # 需人工处理的原因
    remaining_warnings: int = 0                         # 修正后仍剩余的警告数


def _author_zone_bounds(text: str) -> tuple[int, int] | None:
    """作者区 = 条目主体（去掉序号）开头到 [类型标识] 之前。"""
    m = _TAG_RE.search(text)
    if not m:
        return None
    num = _NUM_RE.match(text)
    # start(2) = 序号前缀 "[n] " 之后的主体起点
    body_start = num.start(2) if num else 0
    if m.start() <= body_start:
        return None
    return body_start, m.start()


def fix_entry(text: str, new_index: int) -> EntryFix:
    original = text.strip()
    work = original
    fixes: list[str] = []
    unresolved: list[str] = []

    # 1. 序号：缺号或错号都按新序号重排
    num_m = _NUM_RE.match(work)
    if not num_m:
        work = f"[{new_index}] {work}"
        fixes.append("补齐条目序号")
    else:
        body = num_m.group(2)
        work = f"[{new_index}] {body}"
        if num_m.group(1) != str(new_index):
            fixes.append("重新编号")

    # 2. 全角标点 → 半角
    translated = work.translate(_FULLWIDTH_TRANS)
    if translated != work:
        work = translated
        fixes.append("全角标点改为半角")

    # 3. 尾部句点
    if not work.endswith("."):
        work = work.rstrip() + "."
        fixes.append("补尾部句点")
    work = re.sub(r"\s{2,}", " ", work)

    # 4. 作者区修整：仅当类型标识存在时才可靠
    bounds = _author_zone_bounds(work)
    if bounds:
        zone = work[bounds[0]:bounds[1]]
        has_et_al = ("等" in zone) or ("et al" in zone.lower())
        if not has_et_al:
            core = zone.rstrip()
            ended = core.endswith(".")
            if ended:
                core = core[:-1].rstrip()
            parts = [p.strip() for p in _AUTHOR_SPLIT_RE.split(core) if p.strip()]
            # 每段都短（像作者名）才动手，防止误伤含长标题的解析结果
            if len(parts) >= 4 and all(len(p) <= 40 for p in parts):
                new_zone = ", ".join(parts[:3]) + ", 等" + ("." if ended else "")
                work = work[:bounds[0]] + new_zone + work[bounds[1]:]
                fixes.append("作者超过 3 人，截断为前 3 名并加 “, 等”")

    # 5. 检查无法自动解决的问题（与 checker 的 ERROR 对应）
    if not _TAG_RE.search(work):
        unresolved.append("缺少文献类型标识（[J]/[M]/[D]/[C]/[EB/OL]…），无法自动判断文献类型")
    if not re.search(r"(?:\d{4}|\(\d{4}-\d{2}-\d{2}\))", work):
        unresolved.append("缺少出版年份，请自行补充")
    if "/OL" in work:
        if not re.search(r"https?://", work):
            unresolved.append("电子资源缺少获取路径（网址）")
        if not re.search(r"\[\d{4}-\d{2}-\d{2}\]", work):
            unresolved.append("电子资源建议补充引用日期 [YYYY-MM-DD]")

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
