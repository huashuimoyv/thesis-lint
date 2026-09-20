"""The optional browser acceptance server must not leak a listener after failure."""

import runpy
import socket
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "build" / "verify_web_downloads.py"


@pytest.fixture
def server_tool(tmp_path, monkeypatch):
    tool = runpy.run_path(str(SCRIPT))
    servers, threads = [], []
    namespace = tool["serve_site"].__wrapped__.__globals__

    def record_server(*args, **kwargs):
        server = tool["ThreadingHTTPServer"](*args, **kwargs)
        servers.append(server)
        return server

    def record_thread(*args, **kwargs):
        thread = tool["Thread"](*args, **kwargs)
        threads.append(thread)
        return thread

    monkeypatch.setitem(namespace, "ThreadingHTTPServer", record_server)
    monkeypatch.setitem(namespace, "Thread", record_thread)
    (tmp_path / "index.html").write_text("<p>unique test site</p>", encoding="utf-8")
    return tool, namespace, servers, threads, tmp_path


def assert_closed(servers, threads):
    assert len(servers) == len(threads) == 1
    assert not threads[0].is_alive()
    assert servers[0].socket.fileno() == -1
    with socket.socket() as client:
        client.settimeout(1)
        assert client.connect_ex(servers[0].server_address) != 0


@pytest.mark.parametrize("fail_in_body", [False, True])
def test_serves_exact_site_and_cleans_up_on_normal_or_exception_exit(server_tool, fail_in_body):
    tool, _, servers, threads, folder = server_tool
    try:
        with tool["serve_site"](folder) as url:
            assert url == f"http://127.0.0.1:{servers[0].server_port}"
            tool["check_response"](servers[0], (folder / "index.html").read_bytes())
            if fail_in_body:
                raise ValueError("simulated browser failure")
    except ValueError:
        assert fail_in_body
    assert_closed(servers, threads)


def test_failed_preflight_also_cleans_up(server_tool):
    tool, namespace, servers, threads, folder = server_tool

    def fail(server, expected):
        tool["check_response"](server, b"wrong site")

    namespace["check_response"] = fail
    with (
        pytest.raises(RuntimeError, match=r"requested site's index\.html"),
        tool["serve_site"](folder),
    ):
        pytest.fail("Must not yield before preflight succeeds")
    assert_closed(servers, threads)
