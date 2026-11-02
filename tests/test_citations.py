"""正文引用交叉核对：纯逻辑边界与真实 Word 文档回归。"""

import pytest
from docx import Document

from thesislint.citations import Citation, CitationCheck, check_citations
from thesislint.extractor import Bibliography, find_bibliography_in_document


def bibliography(body, numbers=(1, 2, 3)):
    return Bibliography(
        found=True,
        heading_text="参考文献",
        entries=[f"[{number}] 张三. 文献{number}[J]. 学报, 2024." for number in numbers],
        line_numbers=list(range(len(body) + 2, len(body) + len(numbers) + 2)),
        body_paragraphs=body,
    )


def codes(result):
    return [issue.code for issue in result.issues]


def test_adjacent_grouped_and_repeated_citations():
    result = check_citations(bibliography(["先引用[1][2]，再引用[1,2-3]，重复[3,1]。 "]))

    assert result.checked
    assert result.reason is None
    assert result.issues == []
    assert result.citations == [
        Citation([1], 1, "[1]"),
        Citation([2], 1, "[2]"),
        Citation([1, 2, 3], 1, "[1,2-3]"),
        Citation([3, 1], 1, "[3,1]"),
    ]


@pytest.mark.parametrize("separator", ["-", "‐", "‑", "–", "—", "−", "－", "~", "～", "至"])
def test_chinese_brackets_commas_and_common_ranges(separator):
    raw = f"［ 1， 2 {separator} 3 ］"
    result = check_citations(bibliography([f"正文{raw}。 "]))

    assert result.citations == [Citation([1, 2, 3], 1, raw)]
    assert result.issues == []


def test_list_comma_and_empty_blocks_preserve_locations():
    result = check_citations(bibliography(["标题", "", "引用[1、2、3]。 "]))
    assert result.citations == [Citation([1, 2, 3], 3, "[1、2、3]")]


@pytest.mark.parametrize("raw", ["［１，２－３］", "[１,2-３]", "[1，２、３]"])
def test_fullwidth_and_mixed_digits_match_references_without_changing_raw(raw):
    result = check_citations(bibliography([f"已有研究{raw}。"], ("１", 2, "３")))

    assert result.checked
    assert result.issues == []
    assert result.citations == [Citation([1, 2, 3], 1, raw)]


def test_missing_citation_is_reported_once_and_unused_entry_has_location():
    result = check_citations(bibliography(["", "引用[1][4]，重复[4][1]。"], (1, 2)))

    assert codes(result) == ["S003", "S004"]
    assert "文档块 2" in result.issues[0].message
    assert "[4]" in result.issues[0].message
    assert "文档块 5" in result.issues[1].message
    assert "[2]" in result.issues[1].message
    assert all(issue.level == "WARN" for issue in result.issues)


def test_unused_entry_can_be_reported_without_reference_location():
    bib = bibliography(["引用[1]。"], (1, 2))
    bib.line_numbers = []
    result = check_citations(bib)
    assert codes(result) == ["S004"]
    assert "[2]" in result.issues[0].message


def test_first_citation_should_start_at_one():
    result = check_citations(bibliography(["先引用[2]，后引用[1,3]。 "]))
    assert codes(result) == ["S005", "S005"]
    assert "从 [1] 开始" in result.issues[0].message
    assert "[1] 首次出现于 [2]" in result.issues[1].message


def test_first_citation_order_only_checks_new_numbers():
    result = check_citations(bibliography(["引用[1,3]。", "重复[1,3]后新增[2]。 "]))
    assert codes(result) == ["S005"]
    assert "文档块 2" in result.issues[0].message
    assert "[2] 首次出现于 [3]" in result.issues[0].message


def test_nonexistent_number_does_not_create_order_cascades():
    result = check_citations(bibliography(["引用[99,1-3]。 "]))
    assert codes(result) == ["S003"]


@pytest.mark.parametrize(
    "raw",
    [
        "[2024]",
        "［２０２４］",
        "[０１]",
        "[０]",
        "[１-１０００]",
        "[３-１]",
        "[2024-2025]",
        "[2024-01-01]",
        "[2024/1/1]",
        "[1-9999999999999999999999]",
        "[1-1000]",
        "[0]",
        "[01]",
        "[-1]",
        "[3-1]",
        "[1,3-2]",
        "[1-2-3]",
        "[1,]",
        "[1.2]",
        "[J]",
        "[]",
        "[[1]]",
        "［1]",
        "[1］",
        "[" + "1," * 1100 + "2]",
    ],
)
def test_ambiguous_invalid_or_unbounded_groups_do_not_trigger_unused_warnings(raw):
    result = check_citations(bibliography([f"正文{raw}。 "]))
    assert not result.checked
    assert result.citations == []
    assert result.issues == []
    assert "未识别" in result.reason


def test_largest_supported_range_is_bounded():
    result = check_citations(bibliography(["引用[1-999]。"], range(1, 1000)))
    assert result.checked
    assert result.citations[0].numbers == list(range(1, 1000))
    assert result.issues == []


@pytest.mark.parametrize("body", [[], [""], ["", "  "]])
def test_no_body_is_explained_without_unused_warnings(body):
    result = check_citations(bibliography(body))
    assert not result.checked
    assert not result.has_body
    assert "没有正文" in result.reason
    assert result.issues == []


def test_no_recognizable_citations_is_explained():
    result = check_citations(bibliography(["作者（2024）提出此方法。 "]))
    assert not result.checked
    assert result.has_body
    assert "未识别" in result.reason
    assert result.issues == []


def test_missing_reference_section_is_explained():
    result = check_citations(Bibliography(body_paragraphs=["引用[1]。 "]))
    assert not result.checked
    assert "未找到" in result.reason
    assert result.issues == []


def test_empty_reference_section_is_explained():
    result = check_citations(Bibliography(found=True, body_paragraphs=["引用[1]。 "]))
    assert not result.checked
    assert "章节为空" in result.reason
    assert result.citations == [Citation([1], 1, "[1]")]
    assert result.issues == []


@pytest.mark.parametrize("numbers", [(1, 1), (0,), (-1,), (1000,)])
def test_unreliable_reference_number_mapping_skips_comparison(numbers):
    result = check_citations(bibliography(["引用[1]。"], numbers))
    assert not result.checked
    assert "无法可靠映射" in result.reason
    assert result.citations == [Citation([1], 1, "[1]")]
    assert result.issues == []


def test_missing_reference_number_skips_comparison():
    bib = bibliography(["引用[1]。"])
    bib.entries[0] = "张三. 缺编号文献[J]. 学报, 2024."
    result = check_citations(bib)
    assert not result.checked
    assert "编号缺失" in result.reason
    assert result.citations == [Citation([1], 1, "[1]")]
    assert result.issues == []


def test_gapped_bibliography_numbers_still_have_reliable_mapping():
    result = check_citations(bibliography(["引用[1-3]。"], (1, 3)))
    assert result.checked
    assert codes(result) == ["S003"]


def test_dataclass_lists_are_not_shared():
    first, second = CitationCheck(), CitationCheck()
    first.citations.append(Citation([1], 1, "[1]"))
    assert second.citations == []
    assert Bibliography().body_paragraphs is not Bibliography().body_paragraphs


def test_real_docx_cross_run_table_and_after_bibliography_are_handled(tmp_path):
    document = Document()
    document.add_heading("绪论", level=1)
    document.add_paragraph("")
    paragraph = document.add_paragraph("已有方法")
    paragraph.add_run("[")
    paragraph.add_run("1").font.superscript = True
    paragraph.add_run("]")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "表内证据"
    table.cell(0, 1).text = "［2，3］"
    document.add_heading("参考文献", level=1)
    for number in range(1, 5):
        document.add_paragraph(f"[{number}] 张三. 文献{number}[J]. 学报, 2024.")
    document.add_heading("附录", level=1)
    document.add_paragraph("附录引用[4][99]，不计入正文。")
    path = tmp_path / "body-citations.docx"
    document.save(path)

    bib = find_bibliography_in_document(Document(path))
    result = check_citations(bib)

    assert bib.body_paragraphs == ["绪论", "", "已有方法[1]", "表内证据 ［2，3］"]
    assert result.citations == [Citation([1], 3, "[1]"), Citation([2, 3], 4, "［2，3］")]
    assert codes(result) == ["S004"]
    assert "[4]" in result.issues[0].message
    assert "文档块 9" in result.issues[0].message


def test_real_docx_custom_heading_excludes_bibliography_numbers(tmp_path):
    document = Document()
    document.add_paragraph("正文没有数字引用。")
    document.add_heading("References", level=1)
    document.add_paragraph("[1] 张三. 对照[2]的方法[J]. 学报, 2024.")
    document.add_paragraph("[2] 李四. 文二[J]. 学报, 2024.")
    path = tmp_path / "custom-heading.docx"
    document.save(path)

    bib = find_bibliography_in_document(Document(path), "References")
    result = check_citations(bib)

    assert bib.body_paragraphs == ["正文没有数字引用。"]
    assert not result.checked
    assert result.citations == []
    assert result.issues == []


@pytest.mark.parametrize("heading", ["参考文献", "References"])
def test_body_table_keeps_all_cells_in_one_document_block(tmp_path, heading):
    document = Document()
    table = document.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "[1] Method"
    table.cell(0, 1).text = "[2] Method"
    table.cell(0, 2).text = "More method [3]"
    document.add_paragraph("后接引用[4]。")
    document.add_heading(heading, level=1)
    references = document.add_table(rows=2, cols=2)
    for number, cell in enumerate(references._cells, start=1):
        cell.text = f"[{number}] 张三. 文献{number}[J]. 学报, 2024."
    path = tmp_path / "body-table.docx"
    document.save(path)

    bib = find_bibliography_in_document(Document(path), heading)
    result = check_citations(bib)

    assert bib.body_paragraphs == [
        "[1] Method [2] Method More method [3]",
        "",
        "后接引用[4]。",
    ]
    assert bib.line_numbers == [5, 6, 7, 8]
    assert result.citations == [
        Citation([1], 1, "[1]"),
        Citation([2], 1, "[2]"),
        Citation([3], 1, "[3]"),
        Citation([4], 3, "[4]"),
    ]
    assert result.issues == []


@pytest.mark.parametrize("heading", ["参考文献", "References"])
def test_table_can_contain_body_then_reference_heading_and_entries(heading):
    document = Document()
    table = document.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "正文[1]"
    table.cell(0, 1).text = "和[2]。"
    table.cell(1, 0).merge(table.cell(1, 1)).text = heading
    table.cell(2, 0).text = "[1] 张三. 文一[J]. 学报, 2024."
    table.cell(2, 1).text = "[2] 李四. 文二[J]. 学报, 2024."

    bib = find_bibliography_in_document(document, heading)
    result = check_citations(bib)

    assert bib.body_paragraphs == ["正文[1] 和[2]。"]
    assert bib.line_numbers == [3, 4]
    assert result.checked
    assert result.issues == []
