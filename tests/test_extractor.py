"""extractor 与 CLI 端到端测试（用 python-docx 现场生成样例文档）。"""

from types import SimpleNamespace

import pytest

from thesislint.cli import analyze
from thesislint.extractor import find_bibliography, find_bibliography_in_document


def fake_paragraphs(*pairs):
    """pairs: (text, is_heading) -> 带样式属性的对象列表。"""
    return [
        SimpleNamespace(text=t, style=SimpleNamespace(name="Heading 1" if h else "Normal"))
        for t, h in pairs
    ]


class TestExtractor:
    def test_unnumbered_reference_with_section_word_is_preserved(self):
        entry = "附录编写组. 技术附录[M]. 北京: 出版社, 2024."
        bib = find_bibliography(
            fake_paragraphs(("参考文献", True), (entry, False), ("致谢", False))
        )
        assert bib.entries == [entry]
        assert bib.line_numbers == [2]

    def test_real_heading_still_ends_section_even_with_a_type_marker(self):
        entry = "[1] 张三. 文一[J]. 学报, 2024."
        bib = find_bibliography(
            fake_paragraphs(
                ("参考文献", True),
                (entry, False),
                ("附录：文献类型 [J] 的说明", True),
                ("[2] 不应读入的附录内容", False),
            )
        )
        assert bib.entries == [entry]

    def test_finds_section_between_headings(self):
        paras = fake_paragraphs(
            ("绪论", True),
            ("正文正文。", False),
            ("参考文献", True),
            ("[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.", False),
            ("[2] 李四. 文二[M]. 北京: 出版社, 2020: 1-9.", False),
            ("致谢", True),
            ("感谢大家。", False),
        )
        bib = find_bibliography(paras)
        assert bib.found
        assert len(bib.entries) == 2
        assert bib.entries[0].startswith("[1] 张三")
        assert bib.line_numbers == [4, 5]
        assert bib.body_paragraphs == ["绪论", "正文正文。"]

    def test_merges_wrapped_entry(self):
        paras = fake_paragraphs(
            ("参考文献", True),
            ("[3] 王五, 赵六. 一个标题特别长导致在 Word 里折行的条目[J]. 学报,", False),
            ("2024, 47(3): 100-110.", False),
        )
        bib = find_bibliography(paras)
        assert len(bib.entries) == 1
        assert "2024" in bib.entries[0]

    def test_merges_manual_line_break_inside_paragraph(self):
        paras = fake_paragraphs(
            ("参考文献", True),
            ("[1] 张三. 论文[J].\n学报, 2024, 1(1): 1-9.", False),
        )
        bib = find_bibliography(paras)
        assert bib.entries == ["[1] 张三. 论文[J]. 学报, 2024, 1(1): 1-9."]

    def test_numbered_heading_with_colon(self):
        paras = fake_paragraphs(
            ("第 5 章 参考文献：", False),
            ("[1] 张三. 论文[J]. 学报, 2024, 1(1): 1-9.", False),
        )
        bib = find_bibliography(paras)
        assert bib.found
        assert bib.heading_text == "第 5 章 参考文献："

    def test_deeper_heading_inside_section_is_skipped(self):
        paras = [
            SimpleNamespace(text="参考文献", style=SimpleNamespace(name="Heading 1")),
            SimpleNamespace(text="中文文献", style=SimpleNamespace(name="Heading 2")),
            SimpleNamespace(
                text="[1] 张三. 论文[J]. 学报, 2024, 1(1): 1-9.",
                style=SimpleNamespace(name="Normal"),
            ),
            SimpleNamespace(text="致谢", style=SimpleNamespace(name="Heading 1")),
        ]
        bib = find_bibliography(paras)
        assert len(bib.entries) == 1

    def test_accepts_paragraph_iterables(self):
        paras = iter(
            fake_paragraphs(
                ("参考文献", True),
                ("[1] 张三. 论文[J]. 学报, 2024, 1(1): 1-9.", False),
            )
        )
        assert len(find_bibliography(paras).entries) == 1

    def test_orphan_line_becomes_missing_number_entry(self):
        """区内开头就是无序号正文：必须成为条目交给 checker 报 E001，不得静默跳过。"""
        paras = fake_paragraphs(
            ("参考文献", True),
            ("张三. 丢了序号的条目[J]. 学报, 2024, 1(1): 1-9.", False),
            ("[2] 李四. 正常条目[J]. 学报, 2024, 2(1): 1-9.", False),
        )
        bib = find_bibliography(paras)
        assert len(bib.entries) == 2
        assert bib.entries[0].startswith("张三")

    def test_not_found(self):
        paras = fake_paragraphs(("只有正文", False))
        bib = find_bibliography(paras)
        assert not bib.found
        assert bib.body_paragraphs == ["只有正文"]

    def test_body_empty_blocks_preserve_document_positions(self):
        paras = fake_paragraphs(
            ("", False),
            ("正文[1]。", False),
            ("   ", False),
            ("参考文献", True),
            ("[1] 张三. 文一[J]. 学报, 2024.", False),
        )
        bib = find_bibliography(paras)
        assert bib.body_paragraphs == ["", "正文[1]。", ""]
        assert bib.line_numbers == [5]

    def test_empty_section_keyword_is_not_a_heading(self):
        paras = fake_paragraphs(("参考文献", True))
        assert not find_bibliography(paras, "").found

    def test_multiple_entries_in_one_paragraph(self):
        paras = fake_paragraphs(
            ("参考文献", True),
            ("[1] 张三. 文一[J].\n学报, 2024.\n[2] 李四. 文二[J]. 学报, 2023.", False),
            ("致谢", True),
        )
        bib = find_bibliography(paras)
        assert bib.entries == [
            "[1] 张三. 文一[J]. 学报, 2024.",
            "[2] 李四. 文二[J]. 学报, 2023.",
        ]
        assert bib.line_numbers == [2, 2]

    def test_inline_brackets_are_not_new_entries(self):
        entry = "[1] 张三. 对照 [2] 的方法[J]. 学报, 2024."
        bib = find_bibliography(fake_paragraphs(("参考文献", True), (entry, False)))
        assert bib.entries == [entry]


class TestCliAnalyze:
    @pytest.mark.parametrize("in_table", [False, True])
    def test_section_word_in_reference_continuation_does_not_drop_later_entries(
        self, tmp_path, in_table
    ):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        lines = [
            "[1] 张三. 研究结果与",
            "结论的评估[J]. 学报, 2024.",
            "[2] 李四. 正常条目[J]. 学报, 2023.",
            "致谢",
            "[3] 不应读入的致谢内容",
        ]
        if in_table:
            table = doc.add_table(rows=len(lines), cols=1)
            for row, line in zip(table.rows, lines, strict=True):
                row.cells[0].text = line
        else:
            for line in lines:
                doc.add_paragraph(line)
        path = tmp_path / "wrapped-reference.docx"
        doc.save(path)

        report = analyze(path)

        assert [entry.text for entry in report.entries] == [" ".join(lines[:2]), lines[2]]
        assert [entry.line for entry in report.entries] == [2, 4]

    @pytest.mark.parametrize("keyword", ["Bibliography", "Selected References"])
    @pytest.mark.parametrize("heading_in_table", [False, True])
    def test_custom_plain_heading_is_not_limited_to_ten_characters(
        self, tmp_path, keyword, heading_in_table
    ):
        from docx import Document

        doc = Document()
        body = f"正文提及 {keyword}，不应从这里开始提取。"
        doc.add_paragraph(body)
        if heading_in_table:
            doc.add_table(rows=1, cols=1).cell(0, 0).text = keyword
        else:
            doc.add_paragraph(keyword)
        entry = "[1] Smith J. Title[J]. Journal, 2024, 1(1): 1-9."
        doc.add_paragraph(entry)
        doc.add_paragraph("致谢")
        doc.add_paragraph("不属于参考文献的内容")
        path = tmp_path / "custom-heading.docx"
        doc.save(path)
        original = path.read_bytes()

        report = analyze(path, keyword)

        assert report.found_section
        assert [result.text for result in report.entries] == [entry]
        assert report.entries[0].line == 3
        assert path.read_bytes() == original

    def test_references_in_table_are_extracted_in_document_order(self, tmp_path):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "[1] 张三. 表格中的论文[J]."
        table.cell(0, 1).text = "学报, 2024, 1(1): 1-9."
        table.cell(1, 0).text = "[2] 李四. 表格中的专著[M]."
        table.cell(1, 1).text = "北京: 出版社, 2020."
        doc.add_heading("致谢", level=1)
        path = tmp_path / "table-references.docx"
        doc.save(path)

        report = analyze(path)

        assert [entry.text for entry in report.entries] == [
            "[1] 张三. 表格中的论文[J]. 学报, 2024, 1(1): 1-9.",
            "[2] 李四. 表格中的专著[M]. 北京: 出版社, 2020.",
        ]
        assert [entry.line for entry in report.entries] == [2, 3]

    def test_heading_and_references_can_both_be_inside_table(self):
        from docx import Document

        doc = Document()
        table = doc.add_table(rows=2, cols=1)
        table.cell(0, 0).text = "参考文献"
        table.cell(1, 0).text = "[1] 张三. 表格文献[J]. 学报, 2024, 1(1): 1-9."

        bib = find_bibliography_in_document(doc)

        assert bib.found
        assert bib.entries == ["[1] 张三. 表格文献[J]. 学报, 2024, 1(1): 1-9."]

    def test_table_header_is_ignored_and_two_reference_columns_are_split(self):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "序号"
        table.cell(0, 1).text = "参考文献"
        table.cell(1, 0).text = "[1] 张三. 文一[J]. 学报, 2024."
        table.cell(1, 1).text = "[2] 李四. 文二[J]. 学报, 2023."

        bib = find_bibliography_in_document(doc)

        assert bib.entries == [
            "[1] 张三. 文一[J]. 学报, 2024.",
            "[2] 李四. 文二[J]. 学报, 2023.",
        ]

    def test_empty_or_deeper_heading_does_not_end_reference_table_processing(self):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        doc.add_heading("", level=1)
        doc.add_heading("中文文献", level=2)
        table = doc.add_table(rows=1, cols=2)
        table.cell(0, 0).text = "[1] 张三. 文一[J]. 学报, 2024."
        table.cell(0, 1).text = "[2] 李四. 文二[J]. 学报, 2023."

        bib = find_bibliography_in_document(doc)

        assert len(bib.entries) == 2
        assert bib.line_numbers == [4, 5]

    def test_duplicate_number_after_manual_break_is_reported(self, tmp_path):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        doc.add_paragraph("[1] 张三. 文一[J]. 学报, 2024.\n[1] 李四. 文二[J]. 学报, 2023.")
        path = tmp_path / "multiple-entries.docx"
        doc.save(path)
        report = analyze(path)
        assert len(report.entries) == 2
        assert any(issue.code == "S002" for issue in report.section_issues)

    def test_analyze_real_docx(self, tmp_path):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        doc.add_paragraph("[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.")
        doc.add_paragraph("[2] 李四. 文二. 学报, 2024.")  # 缺类型标识
        doc.add_paragraph("[2] 王五. 文三[J]. 学报, 2024, 1(1): 1-9.")  # 序号重复
        path = tmp_path / "sample.docx"
        doc.save(str(path))

        report = analyze(path)
        assert report.found_section
        assert len(report.entries) == 3
        assert any(i.code == "E002" for i in report.entries[1].issues)
        assert any(i.code == "S002" for i in report.section_issues)

    def test_clean_docx_zero_issues(self, tmp_path):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        doc.add_paragraph("[1] 张三. 文一[J]. 学报, 2024, 1(1): 1-9.")
        path = tmp_path / "clean.docx"
        doc.save(str(path))

        report = analyze(path)
        assert report.error_count == 0
        assert report.warn_count == 0

    def test_real_docx_manual_line_break_is_fully_checked(self, tmp_path):
        from docx import Document

        doc = Document()
        doc.add_heading("参考文献", level=1)
        paragraph = doc.add_paragraph("[1] 张三. 文一[J].")
        paragraph.add_run().add_break()
        paragraph.add_run("学报, 2024, 1(1): 1-9.")
        path = tmp_path / "line-break.docx"
        doc.save(str(path))

        report = analyze(path)
        assert report.error_count == 0
        assert report.warn_count == 0
