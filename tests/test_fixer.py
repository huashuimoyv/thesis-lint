"""fixer 自动修正引擎的单元测试。"""

from thesislint.fixer import fix_entries, fix_entry


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
        assert any("截断" in f for f in r.fixes)

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

    def test_missing_year_marked_unresolved(self):
        r = fix_entry("[2] 李四. 论文名称[J]. 学报.", 2)
        assert any("年份" in u for u in r.unresolved)

    def test_ol_without_url_marked_unresolved(self):
        r = fix_entry("[5] 某机构. 报告[R/OL]. (2024-01-01)[2025-01-01].", 5)
        assert any("网址" in u for u in r.unresolved)

    def test_remaining_warnings_counted(self):
        # 西文姓名未缩写：我们故意不自动修（防止误改），只数剩余警告
        r = fix_entry("[6] Smith John, Lee Bob. A paper[J]. Nature, 2024, 1(1): 1-9.", 6)
        assert r.remaining_warnings >= 1
        assert r.unresolved == []


class TestSectionFixes:
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
