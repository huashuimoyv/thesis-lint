"""fixer 自动修正引擎的单元测试。"""

import pytest

from thesislint.checker import check_entry
from thesislint.fixer import fix_entries, fix_entry
from thesislint.parser import parse_reference


@pytest.mark.parametrize(
    "original",
    [
        "[1] SMITH J. Resource[EB/OL]. (2024-01-01)[2024-02-01]. https://example.org/range:10~20.",
        "[1] SMITH J. Article[J]. Journal, 2024. doi: 10.1234/range:10~20.",
        "[1] SMITH J. Title: 100~110. More title[J]. Journal, 2024.",
        "[1] SMITH J. Title: 100~110. Journal, 2024.",
        "[1] SMITH J. Article[J]. Journal, 2024: https://example.org/resource 10~20.",
        "[1] SMITH J. Article[J]. Journal. doi: 10.1234/abc. Pages: 10~20.",
        "[1] SMITH J. Article[J]. Journal, 123456: 10~20.",
        "[1] SMITH J. Article[J]. Journal, 2024. HTTPS://EXAMPLE.ORG/range:10~20.",
    ],
)
def test_page_correction_preserves_non_page_or_ambiguous_ranges(original):
    result = fix_entry(original, 1)
    assert result.fixed == original
    assert parse_reference(original).page_separator is None
    assert not any(issue.code == "W007" for issue in check_entry(original))
    assert not any("页码区间" in change for change in result.fixes)


@pytest.mark.parametrize("separator", ["~", "～", "–", "—"])
@pytest.mark.parametrize("number", [1, 4])
def test_page_correction_changes_only_pages_and_is_idempotent(separator, number):
    original = (
        f"[{number}] SMITH J. Title: 100~110. More title[J]. Journal, 2024: 10~20. "
        "doi: 10.1234/range:30~40. https://example.org/range:50~60."
    ).replace("2024: 10~20", f"2024: 10{separator}20")
    result = fix_entry(original, 1, renumber=False)
    assert result.fixed == original.replace(f"2024: 10{separator}20", "2024: 10-20")
    assert parse_reference(original).page_range == (10, 20)
    assert fix_entry(result.fixed, 1, renumber=False).fixed == result.fixed


class TestSingleEntryFixes:
    def test_fullwidth_punctuation_fixed(self):
        r = fix_entry("[3] 张三，李四. 论文[J]. 学报，2024，47（3）：100-110.", 3)
        assert r.fixed == "[3] 张三, 李四. 论文[J]. 学报, 2024, 47(3): 100-110."
        assert any("全角" in f for f in r.fixes)
        assert r.unresolved == []

    def test_trailing_period_added(self):
        r = fix_entry("[1] 张三. 论文[J]. 学报, 2024, 1(1): 1-9", 1)
        assert r.fixed.endswith(".")
        assert any("句点" in f for f in r.fixes)

    def test_author_truncation(self):
        r = fix_entry("[4] 张三, 李四, 王五, 赵六. 某研究[J]. 学报, 2024, 1(1): 1-9.", 4)
        assert "张三, 李四, 王五, 等" in r.fixed
        assert "赵六" not in r.fixed
        assert "某研究[J]" in r.fixed
        assert any("截断" in f for f in r.fixes)

    def test_commas_in_title_do_not_trigger_author_truncation(self):
        original = "[1] 张三. 关于甲, 乙, 丙, 丁的研究[J]. 学报, 2024, 1(1): 1-9."
        r = fix_entry(original, 1)
        assert r.fixed == original
        assert not any("截断" in f for f in r.fixes)

    def test_three_authors_untouched(self):
        original = "[1] 张三, 李四, 王五. 某研究[J]. 学报, 2024, 1(1): 1-9."
        r = fix_entry(original, 1)
        assert r.fixed == original
        assert r.fixes == []

    def test_et_al_not_double_appended(self):
        original = "[1] 张三, 李四, 王五, 等. 某研究[J]. 学报, 2024, 1(1): 1-9."
        r = fix_entry(original, 1)
        assert r.fixed == original

    def test_missing_number_added(self):
        r = fix_entry("张三. 论文[J]. 学报, 2024, 1(1): 1-9.", 1)
        assert r.fixed.startswith("[1] 张三")
        assert any("序号" in f for f in r.fixes)

    def test_missing_tag_marked_unresolved(self):
        r = fix_entry("[2] 李四. 论文名称. 学报, 2024, 1(1): 1-9.", 2)
        assert any("类型标识" in u for u in r.unresolved)

    def test_missing_tag_does_not_trigger_author_truncation(self):
        original = "[1] 张三, 李四, 王五, 赵六. 论文名称. 学报, 2024."
        r = fix_entry(original, 1)
        assert r.fixed == original
        assert not any("截断" in f for f in r.fixes)

    def test_missing_year_marked_unresolved(self):
        r = fix_entry("[2] 李四. 论文名称[J]. 学报.", 2)
        assert any("年份" in u for u in r.unresolved)

    def test_ol_without_url_marked_unresolved(self):
        r = fix_entry("[5] 某机构. 报告[R/OL]. (2024-01-01)[2025-01-01].", 5)
        assert any("网址" in u for u in r.unresolved)

    def test_ol_text_outside_type_tag_is_not_treated_as_online(self):
        original = "[1] 张三. A/OL 算法研究[J]. 学报, 2024, 1(1): 1-9."
        r = fix_entry(original, 1)
        assert r.unresolved == []

    def test_remaining_warnings_counted(self):
        # 西文姓名未缩写：我们故意不自动修（防止误改），只数剩余警告
        r = fix_entry("[6] Smith John, Lee Bob. A paper[J]. Nature, 2024, 1(1): 1-9.", 6)
        assert r.remaining_warnings >= 1
        assert r.unresolved == []

    def test_page_range_separator_is_normalized(self):
        r = fix_entry("[1] 张三. 论文[J]. 学报, 2024, 1(1): 100～110.", 1)
        assert r.fixed.endswith("100-110.")
        assert any("页码区间" in f for f in r.fixes)

    def test_reversed_page_range_is_left_for_manual_review(self):
        r = fix_entry("[1] 张三. 论文[J]. 学报, 2024, 1(1): 110-100.", 1)
        assert "110-100" in r.fixed
        assert any("页码" in item for item in r.unresolved)


class TestSectionFixes:
    def test_preserve_numbers_when_body_citations_exist(self):
        entries = [
            "[4] 张三. 文一[J]. 学报，2024，1(1): 1-9",
            "[4] 李四. 文二[J]. 学报, 2024, 2(1): 1-9.",
            "王五. 文三[M]. 北京: 出版社, 2020: 1-9",
        ]
        result = fix_entries(entries, renumber=False)
        assert result["lines"] == [
            "[4] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
            entries[1],
            entries[2] + ".",
        ]
        assert result["summary"]["renumbered"] is False
        assert result["summary"]["manual_needed"] == 3
        assert all(item.unresolved for item in result["results"])
        assert "正文引用" in result["results"][2].unresolved[0]

    def test_preserve_correct_numbers_without_manual_warning(self):
        original = "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9."
        result = fix_entries([original], renumber=False)
        assert result["lines"] == [original]
        assert result["summary"]["manual_needed"] == 0
        assert result["summary"]["auto_fixed"] == 0

    def test_renumbering(self):
        entries = [
            "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
            "[4] 李四. 文二[J]. 学报, 2024, 2(1): 1-9.",
            "王五. 文三[M]. 北京: 出版社, 2020: 1-9.",  # 缺序号
        ]
        result = fix_entries(entries)
        lines = result["lines"]
        assert lines[0].startswith("[1]")
        assert lines[1].startswith("[2]")
        assert lines[2].startswith("[3] 王五")
        assert result["summary"]["renumbered"] is True

    def test_summary_counts(self):
        entries = [
            "[1] 张三，李四. 文一[J]. 学报, 2024, 1(1): 1-9.",  # 可自动修
            "[2] 李四. 文二. 学报, 2024, 1(1): 1-9.",  # 缺类型标识 → 人工
        ]
        result = fix_entries(entries)
        assert result["summary"]["auto_fixed"] >= 1
        assert result["summary"]["manual_needed"] == 1
        assert result["lines"][1].startswith("[2] 李四. 文二. 学报, 2024, 1(1): 1-9.")

    def test_clean_entries_untouched(self):
        entries = ["[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9."]
        result = fix_entries(entries)
        assert result["lines"][0] == entries[0]
        assert result["summary"]["auto_fixed"] == 0
