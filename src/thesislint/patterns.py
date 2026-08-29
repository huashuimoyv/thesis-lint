"""共享正则与字符映射：checker 与 fixer 的唯一事实来源。

为什么单独抽一个模块：
v0.4.0 中 checker 与 fixer 各自定义了一套正则，其中全角字符集不一致
（checker 缺「（）」），导致「检查说不合规、修正却不改」或反之的分歧。
抽出来之后，规则只有一份，从机制上杜绝再次分歧。
"""

from __future__ import annotations

import re

# ---- 条目结构 ----
TAG_RE = re.compile(r"\[([A-Z]{1,2}(?:/[A-Z]{1,2})?)\]")
NUM_RE = re.compile(r"^\[(\d+)\]\s*(.*)$")

# ---- 字段校验 ----
YEAR_RE = re.compile(r"(?:\d{4}|\(\d{4}-\d{2}-\d{2}\))")
URL_RE = re.compile(r"https?://")
CITE_DATE_RE = re.compile(r"\[\d{4}-\d{2}-\d{2}\]")

# ---- 全角标点 ----
# 映射表是唯一事实来源，字符集由它反推，两边不可能再不一致。
FULLWIDTH_MAP: dict[str, str] = {
    "，": ", ",
    "。": ".",
    "；": "; ",
    "：": ": ",
    "（": "(",
    "）": ")",
    "？": "?",
    "！": "!",
}
FULLWIDTH_TRANS = str.maketrans(FULLWIDTH_MAP)
FULLWIDTH_PUNCT = re.compile("[" + "".join(re.escape(c) for c in FULLWIDTH_MAP) + "]")
