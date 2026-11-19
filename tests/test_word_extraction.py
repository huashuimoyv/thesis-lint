"""Word 合并单元格与引用域显示结果的保存重读回归。"""

import pytest
from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from thesislint.checker import check_entries
from thesislint.citations import check_citations
from thesislint.extractor import find_bibliography, find_bibliography_in_document


def _entry(number):
    return f"[{number}] 张三. 文献题名[J]. 学报, 2024."


def _reload(document, tmp_path):
    path = tmp_path / "word-structures.docx"
    document.save(path)
    return Document(path)


def _run(parent, text, tag="w:t"):
    run = OxmlElement("w:r")
    content = OxmlElement(tag)
    content.text = text
    run.append(content)
    parent.append(run)


def _field_marker(parent, kind):
    run = OxmlElement("w:r")
    marker = OxmlElement("w:fldChar")
    marker.set(qn("w:fldCharType"), kind)
    run.append(marker)
    parent.append(run)


def _simple_field(parent, text):
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), " REF _Ref99 \\h ")
    _run(field, text)
    parent.append(field)
    return field


def _inline_content_control(parent, text):
    control = OxmlElement("w:sdt")
    properties = OxmlElement("w:sdtPr")
    alias = OxmlElement("w:alias")
    alias.set(qn("w:val"), "控件属性不是正文[99]")
    properties.append(alias)
    control.append(properties)
    content = OxmlElement("w:sdtContent")
    _run(content, text)
    control.append(content)
    parent.append(control)


def _wrap_blocks_in_content_control(*elements):
    parent = elements[0].getparent()
    control = OxmlElement("w:sdt")
    properties = OxmlElement("w:sdtPr")
    alias = OxmlElement("w:alias")
    alias.set(qn("w:val"), "控件属性不是正文[99]")
    properties.append(alias)
    control.append(properties)
    content = OxmlElement("w:sdtContent")
    control.append(content)
    parent.insert(parent.index(elements[0]), control)
    for element in elements:
        content.append(element)
    return control


@pytest.mark.parametrize("references_in_table", [False, True])
@pytest.mark.parametrize("nested_control", [False, True])
def test_block_content_controls_preserve_section_order_and_positions(
    tmp_path, references_in_table, nested_control
):
    document = Document()
    document.add_paragraph("普通正文[1]。")
    body = document.add_paragraph("控件正文[2]。")
    _wrap_blocks_in_content_control(body._p)
    heading = document.add_heading("参考文献", level=1)
    if references_in_table:
        table = document.add_table(rows=2, cols=1)
        for number, row in enumerate(table.rows, 1):
            row.cells[0].text = _entry(number)
        reference_elements = [table._tbl]
    else:
        reference_elements = [document.add_paragraph(_entry(number))._p for number in (1, 2)]
    end = document.add_heading("致谢", level=1)
    document.add_paragraph("[3] 不属于参考文献的内容")
    control = _wrap_blocks_in_content_control(heading._p, *reference_elements, end._p)
    if nested_control:
        _wrap_blocks_in_content_control(control)

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.found
    assert bib.heading_text == "参考文献"
    assert bib.body_paragraphs == ["普通正文[1]。", "控件正文[2]。"]
    assert bib.entries == [_entry(1), _entry(2)]
    assert bib.line_numbers == [4, 5]
    assert check_citations(bib).checked
    assert check_citations(bib).issues == []


def test_complex_field_state_crosses_block_content_control(tmp_path):
    document = Document()
    start = document.add_paragraph()
    _field_marker(start._p, "begin")
    _run(start._p, " REF [99] ", "w:instrText")
    middle = document.add_paragraph()
    middle.add_run("[98]")
    _wrap_blocks_in_content_control(middle._p)
    end = document.add_paragraph()
    _field_marker(end._p, "separate")
    end.add_run("[1]")
    _field_marker(end._p, "end")
    end.add_run("[2]")
    document.add_heading("参考文献", level=1)
    for number in (1, 2):
        document.add_paragraph(_entry(number))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["", "", "[1][2]"]
    assert bib.line_numbers == [5, 6]
    assert check_citations(bib).issues == []


def test_cell_block_content_control_keeps_entry_breaks_without_reading_nested_tables(tmp_path):
    document = Document()
    document.add_paragraph("正文[1,2]。")
    document.add_heading("参考文献", level=1)
    cell = document.add_table(rows=1, cols=1).cell(0, 0)
    cell.paragraphs[0].text = _entry(1) + "\n" + _entry(2)
    _wrap_blocks_in_content_control(cell.paragraphs[0]._p)
    cell.add_table(rows=1, cols=1).cell(0, 0).text = _entry(99)

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.entries == [_entry(1), _entry(2)]
    assert bib.line_numbers == [3, 3]
    assert check_citations(bib).issues == []


def test_cell_block_content_control_preserves_hidden_field_state(tmp_path):
    document = Document()
    start = document.add_paragraph()
    _field_marker(start._p, "begin")
    table = document.add_table(rows=1, cols=2)
    first = table.cell(0, 0).paragraphs[0]
    first.add_run("[99]")
    _wrap_blocks_in_content_control(first._p)
    second = table.cell(0, 1).paragraphs[0]
    _field_marker(second._p, "separate")
    second.add_run("[1]")
    _field_marker(second._p, "end")
    second.add_run("[2]")
    document.add_heading("参考文献", level=1)
    for number in (1, 2):
        document.add_paragraph(_entry(number))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["", "[1][2]"]
    assert check_citations(bib).issues == []


@pytest.mark.parametrize("in_table", [False, True])
def test_inline_content_control_text_is_preserved_in_body_and_references(tmp_path, in_table):
    document = Document()
    paragraph = (
        document.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
        if in_table
        else document.add_paragraph()
    )
    paragraph.add_run("普通引用[1]，控件引用")
    _inline_content_control(paragraph._p, "[2]")
    document.add_heading("参考文献", level=1)
    document.add_paragraph(_entry(1))
    _inline_content_control(document.add_paragraph()._p, _entry(2))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["普通引用[1]，控件引用[2]"]
    assert bib.entries == [_entry(1), _entry(2)]
    assert bib.line_numbers == [3, 4]
    assert check_citations(bib).issues == []


def test_content_control_inside_field_instructions_is_not_visible_text(tmp_path):
    document = Document()
    paragraph = document.add_paragraph()
    _field_marker(paragraph._p, "begin")
    _inline_content_control(paragraph._p, "[99]")
    _field_marker(paragraph._p, "separate")
    _inline_content_control(paragraph._p, "[1]")
    _field_marker(paragraph._p, "end")
    document.add_heading("参考文献", level=1)
    document.add_paragraph(_entry(1))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["[1]"]
    assert check_citations(bib).issues == []


@pytest.mark.parametrize("break_type", [WD_BREAK.PAGE, WD_BREAK.COLUMN])
def test_explicit_break_keeps_numbered_references_separate(tmp_path, break_type):
    document = Document()
    document.add_paragraph("正文引用[1,2]。")
    document.add_heading("参考文献", level=1)
    paragraph = document.add_paragraph(_entry(1))
    paragraph.add_run().add_break(break_type)
    paragraph.add_run(_entry(2))
    reloaded = _reload(document, tmp_path)

    bib = find_bibliography_in_document(reloaded)

    assert bib.entries == [_entry(1), _entry(2)]
    assert bib.line_numbers == [3, 3]
    assert check_citations(bib).issues == []
    assert find_bibliography(reloaded.paragraphs).entries == bib.entries


def test_automatic_page_marker_does_not_split_a_word(tmp_path):
    document = Document()
    document.add_heading("参考文献", level=1)
    paragraph = document.add_paragraph("[1] 张三. 文献")
    paragraph.add_run()._r.append(OxmlElement("w:lastRenderedPageBreak"))
    paragraph.add_run("题名[J]. 学报, 2024.")

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.entries == [_entry(1)]


@pytest.mark.parametrize("rows, cols", [(1, 2), (2, 1), (2, 2)])
def test_merged_reference_cell_is_read_once_after_roundtrip(tmp_path, rows, cols):
    document = Document()
    document.add_paragraph("已有结果[1,2]。")
    document.add_heading("参考文献", level=1)
    table = document.add_table(rows=rows, cols=cols)
    table.cell(0, 0).merge(table.cell(rows - 1, cols - 1)).text = _entry(1)
    document.add_paragraph(_entry(2))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.entries == [_entry(1), _entry(2)]
    assert bib.line_numbers == [3, rows + 3]
    assert check_entries(bib.entries)[1] == []
    assert check_citations(bib).checked
    assert check_citations(bib).issues == []


def test_identical_independent_cells_are_not_deduplicated(tmp_path):
    document = Document()
    document.add_heading("参考文献", level=1)
    table = document.add_table(rows=2, cols=2)
    for row in table.rows:
        for cell in row.cells:
            cell.text = _entry(1)

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.entries == [_entry(1)] * 4
    assert sum(issue.code == "S002" for issue in check_entries(bib.entries)[1]) == 3


def test_vertical_body_merge_keeps_following_document_positions(tmp_path):
    document = Document()
    table = document.add_table(rows=2, cols=1)
    table.cell(0, 0).merge(table.cell(1, 0)).text = "表内引用[1]。"
    document.add_paragraph("随后引用[2]。")
    document.add_heading("参考文献", level=1)
    document.add_paragraph(_entry(1))
    document.add_paragraph(_entry(2))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["表内引用[1]。", "", "随后引用[2]。"]
    assert [citation.line for citation in check_citations(bib).citations] == [1, 3]
    assert bib.line_numbers == [5, 6]


@pytest.mark.parametrize("in_table", [False, True])
def test_simple_field_result_counts_as_body_citation(tmp_path, in_table):
    document = Document()
    paragraph = (
        document.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
        if in_table
        else document.add_paragraph()
    )
    paragraph.add_run("普通引用[1]，交叉引用")
    _simple_field(paragraph._p, "[2]")
    document.add_heading("参考文献", level=1)
    document.add_paragraph(_entry(1))
    document.add_paragraph(_entry(2))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["普通引用[1]，交叉引用[2]"]
    assert check_citations(bib).checked
    assert check_citations(bib).issues == []


def test_fields_and_hyperlinks_preserve_display_order_without_instructions(tmp_path):
    document = Document()
    paragraph = document.add_paragraph("普通引用[1]")
    parent = paragraph._p
    _field_marker(parent, "begin")
    _run(parent, " REF [99] ", "w:instrText")
    # 嵌套在外层指令中的域结果不是正文；只能读取外层 separator 之后的缓存。
    _simple_field(parent, "[98]")
    _field_marker(parent, "separate")
    _run(parent, "[2]")
    _simple_field(parent, "[3]")
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), "_Ref4")
    _run(hyperlink, "[")
    _run(hyperlink, "4]")
    parent.append(hyperlink)
    _field_marker(parent, "end")
    paragraph.add_run("。")
    document.add_heading("参考文献", level=1)
    for number in range(1, 5):
        document.add_paragraph(_entry(number))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["普通引用[1][2][3][4]。"]
    assert check_citations(bib).issues == []


def test_complex_field_state_survives_paragraph_breaks(tmp_path):
    document = Document()
    first = document.add_paragraph()
    _field_marker(first._p, "begin")
    _run(first._p, " REF [99] ", "w:instrText")
    second = document.add_paragraph()
    _simple_field(second._p, "[98]")
    _field_marker(second._p, "separate")
    second.add_run("证据[1]")
    third = document.add_paragraph()
    _field_marker(third._p, "end")
    third.add_run("后续[2]")
    document.add_heading("参考文献", level=1)
    document.add_paragraph(_entry(1))
    document.add_paragraph(_entry(2))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["", "证据[1]", "后续[2]"]
    assert check_citations(bib).issues == []


@pytest.mark.parametrize("in_table", [False, True])
def test_reference_fields_preserve_manual_entry_breaks(tmp_path, in_table):
    document = Document()
    document.add_heading("参考文献", level=1)
    paragraph = (
        document.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0]
        if in_table
        else document.add_paragraph()
    )
    field = _simple_field(paragraph._p, _entry(1))
    run = OxmlElement("w:r")
    run.append(OxmlElement("w:br"))
    field.append(run)
    _run(field, _entry(2))
    reloaded = _reload(document, tmp_path)

    bib = find_bibliography_in_document(reloaded)

    assert bib.entries == [_entry(1), _entry(2)]
    assert bib.line_numbers == [2, 2]
    if not in_table:
        assert find_bibliography(reloaded.paragraphs).entries == bib.entries


@pytest.mark.parametrize("separate_paragraphs", [False, True])
def test_multicolumn_references_preserve_entry_breaks_inside_each_cell(
    tmp_path, separate_paragraphs
):
    document = Document()
    document.add_paragraph("正文引用[1-3]。")
    document.add_heading("参考文献", level=1)
    table = document.add_table(rows=1, cols=2)
    first_cell = table.cell(0, 0)
    first_cell.paragraphs[0].add_run(_entry(1))
    if separate_paragraphs:
        first_cell.add_paragraph(_entry(2))
    else:
        first_cell.paragraphs[0].add_run().add_break()
        first_cell.paragraphs[0].add_run(_entry(2))
    table.cell(0, 1).text = _entry(3)

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.entries == [_entry(1), _entry(2), _entry(3)]
    assert bib.line_numbers == [3, 3, 4]
    assert check_citations(bib).checked
    assert check_citations(bib).issues == []


def test_complex_field_state_flows_through_body_and_table_cells(tmp_path):
    document = Document()
    paragraph = document.add_paragraph()
    _field_marker(paragraph._p, "begin")
    _run(paragraph._p, " REF [99] ", "w:instrText")
    table = document.add_table(rows=1, cols=2)
    first = table.cell(0, 0).paragraphs[0]
    _field_marker(first._p, "separate")
    first.add_run("[1]")
    table.cell(0, 1).text = "[2]"
    after = document.add_paragraph("[3]")
    _field_marker(after._p, "end")
    after.add_run("后续正文")
    document.add_heading("参考文献", level=1)
    for number in range(1, 4):
        document.add_paragraph(_entry(number))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["", "[1] [2]", "[3]后续正文"]
    assert check_citations(bib).checked
    assert check_citations(bib).issues == []


def test_independent_and_nested_fields_in_merged_cells_do_not_leak_state(tmp_path):
    document = Document()
    document.add_paragraph("正文[1]")
    table = document.add_table(rows=1, cols=3)
    merged = table.cell(0, 0).merge(table.cell(0, 1)).paragraphs[0]
    _field_marker(merged._p, "begin")
    _run(merged._p, " REF [99] ", "w:instrText")
    _field_marker(merged._p, "separate")
    merged.add_run("[2]")
    _field_marker(merged._p, "begin")
    _run(merged._p, " REF [98] ", "w:instrText")
    _field_marker(merged._p, "separate")
    merged.add_run("[3]")
    _field_marker(merged._p, "end")
    _field_marker(merged._p, "end")
    other = table.cell(0, 2).paragraphs[0]
    _field_marker(other._p, "begin")
    _run(other._p, " REF [97] ", "w:instrText")
    _field_marker(other._p, "separate")
    other.add_run("[4]")
    _field_marker(other._p, "end")
    document.add_paragraph("表后[5]")
    document.add_heading("参考文献", level=1)
    for number in range(1, 6):
        document.add_paragraph(_entry(number))

    bib = find_bibliography_in_document(_reload(document, tmp_path))

    assert bib.body_paragraphs == ["正文[1]", "[2][3] [4]", "表后[5]"]
    assert check_citations(bib).checked
    assert check_citations(bib).issues == []
