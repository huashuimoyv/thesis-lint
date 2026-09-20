"""多个真实页码候选应保留原文并解释为何需要人工核对。"""

import pytest

from thesislint.checker import WARN, check_entry
from thesislint.fixer import fix_entries, fix_entry
from thesislint.parser import ReferenceFields, find_page_range, parse_reference


@pytest.mark.parametrize("separator", ["-", "~", "—"])
def test_multiple_publication_page_ranges_are_warned_and_left_unchanged(separator):
    original = (
        f"[4] SMITH J. Article[J]. Journal, 2024: 10{separator}20; supplement: 30{separator}40."
    )

    warnings = [issue for issue in check_entry(original) if issue.code == "W007"]

    assert len(warnings) == 1
    assert warnings[0].level == WARN
    assert "多个页码区间" in warnings[0].message
    assert find_page_range(original) is None
    assert parse_reference(original).page_range_ambiguous
    result = fix_entry(original, 1, renumber=False)
    assert result.fixed == original
    assert warnings[0].message in result.unresolved
    assert any("保留原序号" in message for message in result.unresolved)
    assert result.fixes == []
    assert result.remaining_warnings == 1
    batch = fix_entries([original], renumber=False)
    assert batch["summary"]["manual_needed"] == 1
    assert batch["summary"]["renumbered"] is False


@pytest.mark.parametrize(
    "original",
    [
        "[1] SMITH J. Title: 10~20; part: 30~40[J]. Journal, 2024.",
        "[1] SMITH J. Article[J]. Journal, 2024. https://example.org/p:10~20;q:30~40.",
        "[1] SMITH J. Article[J]. Journal, 2024. doi: 10.1234/p:10~20;q:30~40.",
        "[1] SMITH J. Article[J]. Journal. doi: 10.1234/abc. Pages: 10~20; more: 30~40.",
        "[1] SMITH J. Article. Journal, 2024: 10~20; supplement: 30~40.",
    ],
)
def test_non_publication_candidates_do_not_create_ambiguity_warnings(original):
    assert not parse_reference(original).page_range_ambiguous
    assert not any(issue.code == "W007" for issue in check_entry(original))
    fixed = fix_entry(original, 1)
    assert fixed.fixed == original
    assert not any("多个页码区间" in message for message in fixed.unresolved)


def test_unique_real_pages_still_fix_among_title_and_resource_ranges():
    original = (
        "[1] SMITH J. Title: 10~20; more: 30~40[J]. Journal, 2024: 50~60. "
        "doi: 10.1234/p:70~80. https://example.org/p:90~99."
    )
    fields = parse_reference(original)
    assert not fields.page_range_ambiguous
    assert fields.page_range == (50, 60)
    fixed = fix_entry(original, 1)
    assert fixed.fixed == original.replace("2024: 50~60", "2024: 50-60")
    assert fixed.unresolved == []


def test_reference_fields_existing_positional_construction_remains_valid():
    fields = ReferenceFields(
        1,
        "Article[J]. Journal, 2024.",
        "J",
        "J",
        ("2024",),
        None,
        None,
        False,
        None,
        None,
        None,
        None,
    )
    assert not fields.page_range_ambiguous
