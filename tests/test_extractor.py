"""extractor 与 CLI 端到端测试（用 python-docx 现场生成样例文档）。"""

from types import SimpleNamespace

from thesislint.extractor import find_bibliography
from thesislint.cli import analyze


def fake_paragraphs(*pairs):
    """pairs: (text, is_heading) -> 带样式属性的对象列表。"""
    return [
        SimpleNamespace(text=t, style=SimpleNamespace(name="Heading 1" if h else "Normal"))
        for t, h in pairs
    ]


class TestExtractor:
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

    def test_merges_wrapped_entry(self):
        paras = fake_paragraphs(
            ("参考文献", True),
            ("[3] 王五, 赵六. 一个标题特别长导致在 Word 里折行的条目[J]. 学报,", False),
            ("2024, 47(3): 100-110.", False),
        )
        bib = find_bibliography(paras)
        assert len(bib.entries) == 1
        assert "2024" in bib.entries[0]

    def test_not_found(self):
        paras = fake_paragraphs(("只有正文", False))
        assert not find_bibliography(paras).found


class TestCliAnalyze:
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
