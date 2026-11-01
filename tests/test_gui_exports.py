"""Desktop export and clipboard failures must preserve documents and cached results."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from thesislint import gui


@pytest.fixture
def export_app(tmp_path):
    source = tmp_path / "原始 论文.docx"
    document = Document()
    document.add_paragraph("不可覆盖的原文")
    document.save(source)
    app = gui.App.__new__(gui.App)
    app._last_path = str(source)
    app._md_cache = "# 完整体检报告"
    app._fix_cache = "[4] 原始文献编号."
    app._text_cache = "完整文本报告"
    messages = []
    app._set_status = lambda text, color: messages.append((text, color))
    return app, source, messages


@pytest.mark.parametrize("method", ["export_md", "export_fix_txt"])
@pytest.mark.parametrize("target_kind", ["source", "other_word", "hardlink"])
def test_export_never_overwrites_word_or_source_alias(export_app, method, target_kind):
    app, source, messages = export_app
    original = source.read_bytes()
    if target_kind == "other_word":
        target = source.with_name("另一个文档.DOCX")
        target.write_bytes(original)
    elif target_kind == "hardlink":
        target = source.with_suffix(".txt")
        target.hardlink_to(source)
    else:
        target = source
    app._filedialog = SimpleNamespace(asksaveasfilename=lambda **kw: str(target))

    getattr(app, method)()

    assert source.read_bytes() == original
    assert target.read_bytes() == original
    assert messages[-1][1] == gui.ERR
    assert "覆盖" in messages[-1][0]
    assert app._md_cache == "# 完整体检报告"
    assert app._fix_cache == "[4] 原始文献编号."


@pytest.mark.parametrize("method,extension", [("export_md", ".md"), ("export_fix_txt", ".txt")])
def test_valid_export_keeps_source_intact(export_app, method, extension):
    app, source, messages = export_app
    original = source.read_bytes()
    target = source.with_suffix(extension)
    app._filedialog = SimpleNamespace(asksaveasfilename=lambda **kw: str(target))

    getattr(app, method)()

    assert target.read_text(encoding="utf-8") == (
        app._md_cache if extension == ".md" else app._fix_cache
    )
    assert source.read_bytes() == original
    assert messages[-1][1] == gui.OK


@pytest.mark.parametrize("method", ["export_md", "export_fix_txt"])
def test_cancelled_export_preserves_cache_and_files(export_app, method):
    app, source, messages = export_app
    original = source.read_bytes()
    app._filedialog = SimpleNamespace(asksaveasfilename=lambda **kw: "")
    getattr(app, method)()
    assert not messages
    assert source.read_bytes() == original
    assert app._md_cache and app._fix_cache


@pytest.mark.parametrize("extension", [".doc", ".docm", ".dot", ".dotx", ".dotm"])
def test_export_rejects_other_word_extensions_without_creating_files(export_app, extension):
    app, source, messages = export_app
    target = source.with_suffix(extension)
    app._save_export(str(target), "不能伪装成 Word 的报告")
    assert not target.exists()
    assert messages[-1][1] == gui.ERR


@pytest.mark.parametrize(
    "method,cache", [("copy_report", "_text_cache"), ("copy_fix", "_fix_cache")]
)
@pytest.mark.parametrize("fails_at", ["clear", "append", None])
def test_clipboard_failure_is_recoverable(export_app, method, cache, fails_at):
    app, _, messages = export_app
    content = getattr(app, cache)
    calls = []

    class ClipboardError(Exception):
        pass

    def operation(name, value=None):
        calls.append((name, value))
        if name == fails_at:
            raise ClipboardError("clipboard unavailable")

    app._tk = SimpleNamespace(TclError=ClipboardError)
    app.root = SimpleNamespace(
        clipboard_clear=lambda: operation("clear"),
        clipboard_append=lambda value: operation("append", value),
    )

    getattr(app, method)()

    assert getattr(app, cache) == content
    if fails_at:
        assert "复制失败" in messages[-1][0]
        assert "导出" in messages[-1][0]
        assert messages[-1][1] == gui.WARN
        if fails_at == "clear":
            assert calls == [("clear", None)]
    else:
        assert calls == [("clear", None), ("append", content)]
        assert messages[-1][1] == gui.OK


@pytest.mark.parametrize(
    "method,cache", [("export_md", "_md_cache"), ("export_fix_txt", "_fix_cache")]
)
@pytest.mark.parametrize("already_exists", [False, True])
def test_partial_export_failure_preserves_existing_file_and_cleans_temporary(
    export_app, monkeypatch, method, cache, already_exists
):
    app, source, messages = export_app
    target = source.with_suffix(".txt")
    if already_exists:
        target.write_bytes(b"previous complete report")
    before = set(source.parent.iterdir())
    cached = getattr(app, cache)
    original_write = Path.write_text
    app._filedialog = SimpleNamespace(asksaveasfilename=lambda **kw: str(target))

    def partial_write(path, content, **kwargs):
        original_write(path, content[:2], **kwargs)
        raise OSError("simulated disk full after a partial write")

    monkeypatch.setattr(Path, "write_text", partial_write)
    getattr(app, method)()

    if already_exists:
        assert target.read_bytes() == b"previous complete report"
    else:
        assert not target.exists()
    assert set(source.parent.iterdir()) == before
    assert getattr(app, cache) == cached
    assert messages[-1][1] == gui.ERR


def test_failed_final_replace_preserves_old_report(export_app, monkeypatch):
    app, source, messages = export_app
    target = source.with_suffix(".md")
    target.write_bytes(b"previous complete report")
    before = set(source.parent.iterdir())
    attempts = []

    def denied(path, destination):
        attempts.append((path, destination))
        assert path.parent == target.parent
        assert path.read_text(encoding="utf-8") == app._md_cache
        raise PermissionError("target locked")

    monkeypatch.setattr(Path, "replace", denied)
    app._save_export(str(target), app._md_cache)

    assert len(attempts) == 1
    assert target.read_bytes() == b"previous complete report"
    assert set(source.parent.iterdir()) == before
    assert messages[-1][1] == gui.ERR


def test_invalid_unicode_export_keeps_existing_report(export_app):
    app, source, messages = export_app
    target = source.with_suffix(".md")
    target.write_bytes(b"previous complete report")
    before = set(source.parent.iterdir())

    app._save_export(str(target), "invalid surrogate: \ud800")

    assert target.read_bytes() == b"previous complete report"
    assert set(source.parent.iterdir()) == before
    assert messages[-1][1] == gui.ERR


def test_successful_replace_overwrites_report_only(export_app):
    app, source, messages = export_app
    target = source.with_suffix(".txt")
    target.write_bytes(b"previous complete report")
    source_bytes = source.read_bytes()
    before = set(source.parent.iterdir())

    app._save_export(str(target), app._fix_cache)

    assert target.read_text(encoding="utf-8") == app._fix_cache
    assert source.read_bytes() == source_bytes
    assert set(source.parent.iterdir()) == before
    assert messages[-1][1] == gui.OK
