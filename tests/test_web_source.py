"""网页版关键交互的静态回归保护；完整流程另用真实浏览器验证。"""

import json
from pathlib import Path

import pytest
from docx import Document
from docx.opc.exceptions import PackageNotFoundError

HTML = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")


def test_report_actions_are_connected():
    assert '$("btnCopy").addEventListener("click"' in HTML
    assert '$("btnMd").addEventListener("click"' in HTML
    assert "copyText(reportText," in HTML
    assert 'a.download = "参考文献体检报告.md"' in HTML


def test_report_state_is_cleared_before_new_check():
    assert 'report.textContent = ""' in HTML
    assert 'report.style.display = "none"' in HTML
    assert "hasReport = false" in HTML
    assert "canFix = false" in HTML


def test_untrusted_reference_text_is_not_inserted_as_html():
    assert "m.append(document.createTextNode(" in HTML
    assert "manual.map" not in HTML


def test_status_messages_do_not_use_html_rendering():
    status_source = HTML.split("function setStage(", 1)[1].split("/*", 1)[0]
    assert "innerHTML" not in status_source
    assert "document.createTextNode(" in status_source
    assert 'document.createElement("span")' in status_source


def test_long_status_tokens_can_wrap_without_clipping_error_details():
    status_style = HTML.split("#stage {", 1)[1].split("}", 1)[0]
    assert "overflow-wrap: anywhere" in status_style
    assert "overflow: hidden" not in status_style
    assert "text-overflow: ellipsis" not in status_style


def test_upload_is_focusable_and_keyboard_activation_is_guarded():
    upload_tag = HTML.split('<div id="drop"', 1)[1].split(">", 1)[0]
    assert 'tabindex="0"' in upload_tag
    key_handler = HTML.split('drop.addEventListener("keydown",', 1)[1].split("});", 1)[0]
    assert "e.target !== drop" in key_handler
    assert 'e.key !== "Enter"' in key_handler and 'e.key !== " "' in key_handler
    assert "e.preventDefault()" in key_handler
    assert "e.repeat" in key_handler
    click_handler = HTML.split('drop.addEventListener("click",', 1)[1].split("});", 1)[0]
    assert "if (busy) return" in click_handler
    assert 'drop.setAttribute("aria-disabled", String(busy))' in HTML


def test_report_filters_are_connected_and_exports_stay_complete():
    assert 'data-report-filter="error"' in HTML
    assert 'data-report-filter="warn"' in HTML
    assert 'button.addEventListener("click", () => renderReport' in HTML
    assert (
        "reportViews = { all: data.text, error: data.text_errors, warn: data.text_warnings }"
        in HTML
    )
    assert "copyText(reportText," in HTML


def test_official_rule_basis_is_linked():
    assert "openstd.samr.gov.cn/bzgk/std/newGbInfo" in HTML


@pytest.fixture
def web_backend():
    """执行页面实际嵌入的 Python 胶水，覆盖本地引擎与 UI 数据契约。"""
    source = HTML.split("const PY_SETUP = `", 1)[1].split("`;", 1)[0]
    namespace = {}
    exec(compile(source, "web/index.html:PY_SETUP", "exec"), namespace)
    return namespace


@pytest.mark.parametrize(
    "body,extra_entry",
    [
        ("已有研究见[4]，待核对的引用见[9]。", None),
        ("已有研究见[4]。", "李四. 缺号标题[J]. 学报, 2024"),
        ("已有研究见[4]。", "[4] 李四. 重号标题[J]. 学报, 2024"),
        ("正文没有可识别的引用编号。", None),
        ("正文引用使用了超出支持范围的[1000]。", None),
    ],
)
def test_web_fix_preserves_displayed_citations_after_file_changes(
    tmp_path, web_backend, body, extra_entry
):
    path = tmp_path / "论文.docx"
    doc = Document()
    doc.add_paragraph(body)
    doc.add_heading("参考文献", level=1)
    original = "[4] 张三. 原始标题[J]. 学报，2024，1(1): 1-9"
    if extra_entry:
        doc.add_paragraph(extra_entry)
    doc.add_paragraph(original)
    doc.save(path)
    report = json.loads(web_backend["web_check"](str(path)))
    if extra_entry:
        assert web_backend["checked_report"].citations.checked is False
        assert "无法可靠映射" in report["text"]
    elif "[9]" in body:
        assert "S003" in report["text"]
        assert "S003" in report["markdown"]
        assert "S003" in report["text_warnings"]
    assert "S003" not in report["text_errors"]

    doc.paragraphs[0].text = "新正文没有引用编号。"
    doc.paragraphs[-1].text = "[1] 李四. 后来修改的标题[J]. 学报, 2025."
    doc.save(path)
    result = json.loads(web_backend["web_fix"](str(path)))
    assert result["preserve_numbers"] is True
    expected_lines = []
    if extra_entry:
        expected_lines.append(extra_entry + ".")
    expected_lines.append("[4] 张三. 原始标题[J]. 学报, 2024, 1(1): 1-9.")
    assert result["lines"] == expected_lines
    assert result["summary"]["renumbered"] is False

    doc.paragraphs[0].text = ""
    doc.save(path)
    web_backend["web_check"](str(path))
    next_result = json.loads(web_backend["web_fix"](str(path)))
    assert next_result["preserve_numbers"] is False
    assert "后来修改" in next_result["lines"][-1]


def test_web_failed_check_cannot_reuse_previous_snapshot(tmp_path, web_backend):
    path = str(tmp_path / "示例.docx")
    web_backend["web_demo"](path)
    with pytest.raises(ValueError, match="先检查"):
        web_backend["web_fix"](str(tmp_path / "另一份.docx"))
    with pytest.raises(PackageNotFoundError):
        web_backend["web_check"](str(tmp_path / "不存在.docx"))
    with pytest.raises(ValueError, match="先检查"):
        web_backend["web_fix"](path)


def test_web_demo_includes_body_citation_review(tmp_path, web_backend):
    report = json.loads(web_backend["web_demo"](str(tmp_path / "示例.docx")))
    assert all(code in report["text_warnings"] for code in ("S003", "S004", "S005"))
    assert "正文引用核对" in report["text"]
