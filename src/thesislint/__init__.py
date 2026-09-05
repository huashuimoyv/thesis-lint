"""thesis-lint —— 毕业论文「国标体检」工具。

检查 Word (.docx) 论文的参考文献是否符合 GB/T 7714-2025。
"""

__version__ = "0.6.2"

from .checker import Issue, check_entries, check_entry
from .extractor import find_bibliography
from .report import build_text_report

__all__ = [
    "Issue",
    "__version__",
    "build_text_report",
    "check_entries",
    "check_entry",
    "find_bibliography",
]
