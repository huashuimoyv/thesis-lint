"""Demo documents belong to one analysis job and never require a real Tk window."""

import queue
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from thesislint import cli, gui


@pytest.fixture
def demo_app(tmp_path, monkeypatch):
    temporary_directory = tempfile.TemporaryDirectory
    directories = []

    def create_directory(*args, **kwargs):
        kwargs["dir"] = tmp_path
        directory = temporary_directory(*args, **kwargs)
        directories.append(directory)
        return directory

    # Also keep the old fixed-path implementation inside this test's own directory.
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(tempfile, "TemporaryDirectory", create_directory)
    app = gui.App.__new__(gui.App)
    app._closed = False
    app._job_id = 0
    app._last_path = "previous.docx"
    app._text_cache = app._md_cache = app._fix_cache = "previous result"
    app._ui_callbacks = queue.SimpleQueue()
    app._after_ids = set()
    app.root = SimpleNamespace()
    messages = []
    app._set_status = lambda message, color: messages.append((message, color))
    app._messagebox = SimpleNamespace(showwarning=lambda *args: messages.append(args))
    app._finish_error = lambda job_id, detail: app._set_status(detail, gui.ERR)
    app._show_drop_state = lambda mode: None
    app._set_stage = lambda *args, **kwargs: None
    app._set_enabled = lambda *args: None
    widget = SimpleNamespace(configure=lambda **kwargs: None)
    for name in (
        "busy_name",
        "drop",
        "btn_copy",
        "btn_md",
        "btn_fix",
        "btn_fix_copy",
        "btn_fix_txt",
    ):
        setattr(app, name, widget)

    def clear_results():
        app._text_cache = app._md_cache = app._fix_cache = ""

    app._clear_result_views = clear_results
    yield app, directories, messages
    for directory in directories:
        directory.cleanup()


@pytest.fixture
def deferred_jobs(monkeypatch):
    jobs = []

    def create_thread(*, target, args, daemon):
        assert daemon
        return SimpleNamespace(start=lambda: jobs.append((target, args)))

    monkeypatch.setattr(gui.threading, "Thread", create_thread)
    return jobs


def test_repeated_demo_jobs_are_isolated_and_clean_up_independently(
    demo_app, deferred_jobs, tmp_path
):
    app, directories, _ = demo_app
    existing = tmp_path / "thesislint_demo.docx"
    original = Document()
    original.add_paragraph("Unrelated existing document")
    original.save(existing)
    original_bytes = existing.read_bytes()

    app.check_demo()
    app.check_demo()
    paths = [Path(args[0]) for _, args in deferred_jobs]

    assert len(paths) == 2
    assert paths[0].parent != paths[1].parent
    assert all(path.is_file() for path in paths)
    assert existing.read_bytes() == original_bytes
    deferred_jobs[0][0](*deferred_jobs[0][1])
    assert not paths[0].parent.exists()
    assert paths[1].is_file()
    # The stale first result must still be ignored after a newer demo starts.
    app._ui_callbacks.get_nowait()()
    assert app._text_cache == ""
    deferred_jobs[1][0](*deferred_jobs[1][1])
    assert len(directories) == 2
    assert not any(Path(directory.name).exists() for directory in directories)
    assert existing.read_bytes() == original_bytes


@pytest.mark.parametrize("stage", ["directory", "document", "save"])
def test_demo_generation_failure_keeps_old_results_and_cleans_resources(
    demo_app, deferred_jobs, monkeypatch, stage
):
    app, directories, messages = demo_app

    def fail(*args, **kwargs):
        raise PermissionError("synthetic demo generation failure")

    if stage == "directory":
        monkeypatch.setattr(tempfile, "TemporaryDirectory", fail)
    elif stage == "document":
        monkeypatch.setattr("docx.Document", fail)
    else:
        from docx.document import Document as DocumentClass

        save = DocumentClass.save

        def failed_save(document, path):
            save(document, path)
            fail()

        monkeypatch.setattr(DocumentClass, "save", failed_save)

    app.check_demo()

    assert not deferred_jobs
    assert app._text_cache == app._md_cache == app._fix_cache == "previous result"
    assert app._last_path == "previous.docx"
    assert "无法生成示例" in messages[-1][0]
    assert messages[-1][1] == gui.ERR
    assert not any(Path(directory.name).exists() for directory in directories)


@pytest.mark.parametrize("stage", ["construct", "start"])
def test_demo_thread_start_failure_cleans_resources(demo_app, monkeypatch, stage):
    app, directories, messages = demo_app

    def fail():
        raise RuntimeError("synthetic worker start failure")

    def create_thread(**kwargs):
        if stage == "construct":
            fail()
        return SimpleNamespace(start=fail)

    monkeypatch.setattr(gui.threading, "Thread", create_thread)
    app.check_demo()

    assert directories
    assert not any(Path(directory.name).exists() for directory in directories)
    assert "synthetic worker start failure" in messages[-1][0]
    assert messages[-1][1] == gui.ERR


@pytest.mark.parametrize("reason", ["extension", "missing", "closed"])
def test_check_early_return_cleans_owned_demo_directory(demo_app, deferred_jobs, reason):
    app, _, _ = demo_app
    directory = tempfile.TemporaryDirectory(prefix="owned-demo-")
    path = Path(directory.name) / ("demo.txt" if reason == "extension" else "demo.docx")
    if reason != "missing":
        Document().save(path)
    if reason == "closed":
        app._closed = True

    app.check(str(path), _temporary_dir=directory)

    assert not deferred_jobs
    assert not Path(directory.name).exists()
    assert app._text_cache == "previous result"


@pytest.mark.parametrize("fails", [False, True])
def test_closing_window_does_not_remove_demo_while_worker_is_reading(demo_app, monkeypatch, fails):
    app, directories, _ = demo_app
    original_analyze = cli.analyze
    original_thread = threading.Thread
    entered = threading.Event()
    release = threading.Event()
    threads = []
    errors = []
    active_paths = []

    def blocked_analyze(path):
        active_paths.append(path)
        with path.open("rb"):
            entered.set()
            assert release.wait(5), "test did not release demo reader"
            assert path.is_file()
            if fails:
                raise ValueError("synthetic analysis failure")
            return original_analyze(path)

    def create_thread(*, target, args, daemon):
        def run():
            try:
                target(*args)
            except Exception as exc:  # noqa: BLE001  capture worker failures for the assertion
                errors.append(exc)

        thread = original_thread(target=run, daemon=daemon)
        threads.append(thread)
        return thread

    monkeypatch.setattr(cli, "analyze", blocked_analyze)
    monkeypatch.setattr(gui.threading, "Thread", create_thread)
    try:
        app.check_demo()
        assert entered.wait(3)
        app._on_destroy(SimpleNamespace(widget=app.root))
        assert app._closed
        assert active_paths[0].is_file()
    finally:
        release.set()
        for thread in threads:
            thread.join(4)

    assert threads and not any(thread.is_alive() for thread in threads)
    assert not errors
    assert directories
    assert not active_paths[0].exists()
    assert not any(Path(directory.name).exists() for directory in directories)
    assert app._ui_callbacks.empty()


def test_analysis_failure_cleans_demo_before_delivering_error(demo_app, deferred_jobs, monkeypatch):
    app, directories, messages = demo_app

    def fail(path):
        raise ValueError("synthetic invalid document")

    monkeypatch.setattr(cli, "analyze", fail)
    app.check_demo()
    deferred_jobs[0][0](*deferred_jobs[0][1])

    assert directories and not Path(directories[0].name).exists()
    app._ui_callbacks.get_nowait()()
    assert messages[-1] == ("synthetic invalid document", gui.ERR)


def test_normal_document_is_never_cleaned_up(demo_app, deferred_jobs, tmp_path):
    app, directories, _ = demo_app
    path = tmp_path / "user-document.docx"
    Document().save(path)
    original = path.read_bytes()

    app.check(str(path))
    assert len(deferred_jobs[0][1]) == 3
    deferred_jobs[0][0](*deferred_jobs[0][1])

    assert not directories
    assert path.read_bytes() == original


def test_cleanup_failure_does_not_hide_demo_generation_error(demo_app, monkeypatch):
    app, _, messages = demo_app
    directory = tempfile.TemporaryDirectory(prefix="cleanup-failure-")

    def generation_failure():
        raise ValueError("original generation failure")

    def cleanup_failure():
        raise OSError("synthetic cleanup refusal")

    with monkeypatch.context() as patch:
        patch.setattr(tempfile, "TemporaryDirectory", lambda **kwargs: directory)
        patch.setattr("docx.Document", generation_failure)
        patch.setattr(directory, "cleanup", cleanup_failure)
        app.check_demo()

    assert "original generation failure" in messages[-1][0]
    assert "synthetic cleanup refusal" not in messages[-1][0]
    assert app._text_cache == app._md_cache == app._fix_cache == "previous result"


@pytest.mark.parametrize("analysis_fails", [False, True])
def test_worker_cleanup_failure_does_not_drop_result(
    demo_app, deferred_jobs, monkeypatch, analysis_fails
):
    app, directories, _ = demo_app
    results = []
    app._finish = lambda *args: results.append("success")
    app._finish_error = lambda job_id, detail: results.append(detail)

    def analysis_failure(path):
        raise ValueError("original analysis failure")

    def cleanup_failure():
        raise OSError("synthetic cleanup refusal")

    if analysis_fails:
        monkeypatch.setattr(cli, "analyze", analysis_failure)
    app.check_demo()
    with monkeypatch.context() as patch:
        patch.setattr(directories[0], "cleanup", cleanup_failure)
        deferred_jobs[0][0](*deferred_jobs[0][1])

    app._ui_callbacks.get_nowait()()
    assert results == ["original analysis failure" if analysis_fails else "success"]
