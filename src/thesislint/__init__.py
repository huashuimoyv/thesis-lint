"""thesis-lint —— 毕业论文「国标体检」工具。

检查 Word (.docx) 论文的参考文献是否符合 GB/T 7714-2025。
"""

__version__ = "0.2.0"

from .checker import Issue, check_entry, check_entries
from .extractor import find_bibliography
from .report import build_text_report

__all__ = [
    "Issue",
    "check_entry",
    "check_entries",
    "find_bibliography",
    "build_text_report",
    "__version__",
]
