"""checker 规则单元测试。"""

from thesislint.checker import ERROR, WARN, check_entries, check_entry


class TestValidEntries:
    def test_valid_journal(self):
        entry = "[1] 张三, 李四. 一种论文格式检查方法[J]. 计算机学报, 2024, 47(3): 100-110."
        assert check_entry(entry) == []

    def test_valid_book(self):
        entry = "[2] 王五. 数据结构[M]. 北京: 清华大学出版社, 2020: 55-60."
        assert check_entry(entry) == []

    def test_valid_online_with_cite_date(self):
        entry = (
            "[3] 中国互联网络信息中心. 第53次中国互联网络发展状况统计报告[R/OL]. "
            "(2024-03-22)[2025-01-10]. https://www.cnnic.net.cn/n4/2024/0322/c88-10964.html."
        )
        assert check_entry(entry) == []


class TestErrors:
    def test_missing_number(self):
        issues = check_entry("张三. 论文[J]. 学报, 2024, 1(1): 1-9.")
        assert any(i.code == "E001" and i.level == ERROR for i in issues)

    def test_missing_tag(self):
        issues = check_entry("[1] 张三. 论文名称. 学报, 2024, 1(1): 1-9.")
        assert any(i.code == "E002" for i in issues)

    def test_online_without_url(self):
        issues = check_entry("[1] 某某机构. 报告[R/OL]. (2024-01-01)[2025-01-01].")
        assert any(i.code == "E003" and i.level == ERROR for i in issues)

    def test_online_accepts_uppercase_url_scheme(self):
        entry = "[1] 某机构. 报告[R/OL]. (2024-01-01)[2025-01-01]. HTTPS://EXAMPLE.COM."
        assert not any(i.code == "E003" for i in check_entry(entry))

    def test_missing_year(self):
        issues = check_entry("[1] 张三. 论文名称[J]. 计算机学报.")
        assert any(i.code == "E004" for i in issues)


class TestWarnings:
    def test_too_many_authors_without_et_al(self):
        entry = "[1] 张三, 李四, 王五, 赵六. 论文名称[J]. 学报, 2024, 1(1): 1-9."
        codes = [i.code for i in check_entry(entry)]
        assert "W003" in codes

    def test_commas_in_title_are_not_counted_as_authors(self):
        entry = "[1] 张三. 关于甲, 乙, 丙, 丁的研究[J]. 学报, 2024, 1(1): 1-9."
        codes = [i.code for i in check_entry(entry)]
        assert "W003" not in codes

    def test_three_authors_with_et_al_ok(self):
        entry = "[1] 张三, 李四, 王五, 等. 论文名称[J]. 学报, 2024, 1(1): 1-9."
        codes = [i.code for i in check_entry(entry)]
        assert "W003" not in codes

    def test_et_al_accepted_for_western_entries(self):
        entry = (
            "[2] Vaswani A, Shazeer N, Parmar J, et al. "
            "Attention is all you need[C]//NeurIPS. 2017: 5998-6008."
        )
        codes = [i.code for i in check_entry(entry)]
        assert "W003" not in codes

    def test_western_full_given_name(self):
        entry = "[1] Smith John, Lee Bob. A paper on checking[J]. Nature, 2024, 1(1): 1-9."
        codes = [i.code for i in check_entry(entry)]
        assert "W004" in codes

    def test_fullwidth_punctuation(self):
        entry = "[1] 张三，李四. 论文名称[J]. 学报，2024，1（1）：1-9."
        codes = [i.code for i in check_entry(entry)]
        assert "W005" in codes

    def test_no_trailing_period(self):
        entry = "[1] 张三. 论文名称[J]. 学报, 2024, 1(1): 1-9"
        codes = [i.code for i in check_entry(entry)]
        assert "W006" in codes

    def test_online_without_cite_date(self):
        entry = "[1] 某某机构. 报告[R/OL]. (2024-01-01). https://example.com/r.pdf."
        codes = [i.code for i in check_entry(entry)]
        assert "W002" in codes

    def test_unknown_tag(self):
        entry = "[1] 张三. 论文名称[X]. 学报, 2024, 1(1): 1-9."
        codes = [i.code for i in check_entry(entry)]
        assert "W001" in codes

    def test_reversed_page_range(self):
        entry = "[1] 张三. 论文名称[J]. 学报, 2024, 1(1): 110-100."
        issues = check_entry(entry)
        assert any(i.code == "W007" and i.level == WARN for i in issues)

    def test_nonstandard_page_range_separator(self):
        entry = "[1] 张三. 论文名称[J]. 学报, 2024, 1(1): 100～110."
        assert any(i.code == "W007" for i in check_entry(entry))

    def test_valid_article_number_is_not_treated_as_bad_pages(self):
        entry = "[1] 张三. 论文名称[J]. 学报, 2024, 12(2): e10345."
        assert not any(i.code == "W007" for i in check_entry(entry))

    def test_invalid_doi_format(self):
        entry = "[1] 张三. 论文名称[J]. 学报, 2024. doi: 10.12/bad."
        issues = check_entry(entry)
        assert any(i.code == "W008" and i.level == WARN for i in issues)

    def test_valid_doi_url(self):
        entry = "[1] 张三. 论文名称[J]. 学报, 2024. https://doi.org/10.1000/xyz-123."
        assert not any(i.code == "W008" for i in check_entry(entry))

    def test_missing_doi_is_not_an_issue(self):
        entry = "[1] 张三. 论文名称[J]. 学报, 2024, 1(1): 1-9."
        assert not any(i.code == "W008" for i in check_entry(entry))

    def test_decimal_version_number_is_not_treated_as_doi(self):
        entry = "[1] 张三. Python 3.10 使用指南[M]. 北京: 出版社, 2024."
        assert not any(i.code == "W008" for i in check_entry(entry))

    def test_print_monograph_without_publication_item(self):
        entry = "[1] 王五. 数据结构[M]. 2020."
        assert any(i.code == "W009" for i in check_entry(entry))

    def test_online_monograph_does_not_require_print_publication_item(self):
        entry = "[1] 王五. 在线专著[M/OL]. 2020[2026-09-05]. https://example.com/book."
        assert not any(i.code == "W009" for i in check_entry(entry))


class TestSectionRules:
    def test_duplicate_numbers(self):
        entries = [
            "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
            "[1] 李四. 文二[J]. 学报, 2024, 2(1): 1-9.",
        ]
        _, section_issues = check_entries(entries)
        assert any(i.code == "S002" and i.level == ERROR for i in section_issues)

    def test_number_gap(self):
        entries = [
            "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
            "[3] 李四. 文二[J]. 学报, 2024, 2(1): 1-9.",
        ]
        _, section_issues = check_entries(entries)
        assert any(i.code == "S001" and i.level == WARN for i in section_issues)

    def test_clean_section_has_no_section_issues(self):
        entries = [
            "[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.",
            "[2] 李四. 文二[M]. 北京: 出版社, 2020: 1-9.",
        ]
        per_entry, section_issues = check_entries(entries)
        assert all(x == [] for x in per_entry)
        assert section_issues == []
