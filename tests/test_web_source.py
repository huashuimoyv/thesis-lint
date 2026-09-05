"""网页版关键交互的静态回归保护；完整流程另用真实浏览器验证。"""

from pathlib import Path

HTML = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")


def test_report_actions_are_connected():
    assert '$("btnCopy").addEventListener("click"' in HTML
    assert '$("btnMd").addEventListener("click"' in HTML
    assert "navigator.clipboard.writeText(reportText)" in HTML
    assert 'a.download = "参考文献体检报告.md"' in HTML


def test_report_state_is_cleared_before_new_check():
    assert 'report.textContent = ""' in HTML
    assert 'report.style.display = "none"' in HTML
    assert "hasReport = false" in HTML
    assert "canFix = false" in HTML


def test_untrusted_reference_text_is_not_inserted_as_html():
    assert "m.append(document.createTextNode(" in HTML
    assert "manual.map" not in HTML


def test_report_filters_are_connected_and_exports_stay_complete():
    assert 'data-report-filter="error"' in HTML
    assert 'data-report-filter="warn"' in HTML
    assert 'button.addEventListener("click", () => renderReport' in HTML
    assert (
        "reportViews = { all: data.text, error: data.text_errors, warn: data.text_warnings }"
        in HTML
    )
    assert "navigator.clipboard.writeText(reportText)" in HTML


def test_official_rule_basis_is_linked():
    assert "openstd.samr.gov.cn/bzgk/std/newGbInfo" in HTML
