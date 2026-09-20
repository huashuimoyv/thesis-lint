"""出版年份与题名、资源标识、引用日期和页码必须区分。"""

import pytest

from thesislint.checker import check_entry
from thesislint.fixer import fix_entry
from thesislint.parser import parse_reference


@pytest.mark.parametrize(
    "entry",
    [
        "[1] SMITH J. Article[J]. Journal. doi: 10.1234/abc.",
        "[1] SMITH J. Article[J]. Journal. https://example.com/2024/article.",
        "[1] SMITH J. Trends in 2024[J]. Journal.",
        "[1] SMITH J. Article[J]. Journal, 12(2): 2024-2029.",
        "[1] SMITH J. Article[J]. Journal, 123456.",
        "[1] SMITH J. Article[J]. Journal, e2024.",
        "[1] SMITH J. Article[J]. Journal, 12(2024): 1-9.",
        "[1] SMITH J. Resource[EB/OL]. [2024-01-01]. https://example.com/resource.",
    ],
)
def test_non_publication_digits_do_not_hide_missing_year(entry):
    assert parse_reference(entry).years == ()
    assert any(issue.code == "E004" for issue in check_entry(entry))
    result = fix_entry(entry, 1)
    assert result.fixed == entry
    assert any("年份" in message for message in result.unresolved)


@pytest.mark.parametrize(
    "entry,years",
    [
        ("[1] 张三. 2023 年研究[J]. 学报, 2024, 12(2): 2025-2029.", ("2024",)),
        ("[1] 张三. 研究[J]. 学报，2024，12（2）：2025-2029.", ("2024",)),
        ("[1] 张三. 研究[M]. 北京: 出版社, 2020: 2021-2029.", ("2020",)),
        ("[1] 张三. 研究[J]. 学报, [2024]: 1-9.", ("2024",)),
        ("[1] 张三. 研究. 学报, 2024: 1-9.", ("2024",)),
        (
            "[1] 张三. 报告[R/OL]. (2024-01-01)[2025-01-01]. https://example.com/2026.",
            ("2024",),
        ),
    ],
)
def test_publication_year_is_shared_between_check_and_fix(entry, years):
    assert parse_reference(entry).years == years
    assert not any(issue.code == "E004" for issue in check_entry(entry))
    assert not any("年份" in message for message in fix_entry(entry, 1).unresolved)
