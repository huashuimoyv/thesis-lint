"""Opt-in real browser download acceptance; never changes browser policy or user data."""

import argparse
from contextlib import contextmanager
from functools import partial
from http.client import HTTPConnection
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def check_response(server, expected):
    connection = HTTPConnection(*server.server_address, timeout=5)
    try:
        connection.request("GET", "/index.html")
        response = connection.getresponse()
        body = response.read()
        if response.status != 200 or body != expected:
            raise RuntimeError("Local server did not return the requested site's index.html")
    finally:
        connection.close()


@contextmanager
def serve_site(directory):
    """Own one loopback socket and service thread, including on failed preflight/tests."""
    directory = Path(directory).resolve()
    expected = (directory / "index.html").read_bytes()
    handler = partial(QuietHandler, directory=str(directory))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            check_response(server, expected)
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("Local HTTP server thread did not stop")


def verify_downloads(site_dir, output_dir):
    # Optional tool: ordinary pytest runs do not need Playwright or a browser installed.
    from playwright.sync_api import expect, sync_playwright

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    with serve_site(site_dir) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(accept_downloads=True)
            page.set_default_timeout(45000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{url}/?autodemo=1&autofix=1&theme=light")
            page.wait_for_load_state("networkidle")
            expect(page.locator("#fixPanel")).to_be_visible()
            with page.expect_download(timeout=10000) as event:
                page.locator("#btnMd").click()
            unfiltered = event.value
            assert unfiltered.failure() is None
            original_report = Path(unfiltered.path()).read_bytes()
            page.locator('[data-report-filter="error"]').click()
            assert "W005" not in page.locator("#report").inner_text()

            with page.expect_download(timeout=10000) as event:
                page.locator("#btnMd").click()
            markdown = event.value
            assert markdown.failure() is None
            assert markdown.suggested_filename == "参考文献体检报告.md"
            markdown_path = output_dir / markdown.suggested_filename
            markdown.save_as(markdown_path)
            assert markdown_path.read_bytes() == original_report
            report = markdown_path.read_text(encoding="utf-8")
            assert "W005" in report and "S003" in report

            with page.expect_download(timeout=10000) as event:
                page.locator("#btnFixTxt").click()
            text = event.value
            assert text.failure() is None
            assert text.suggested_filename == "参考文献_修正后.txt"
            text_path = output_dir / text.suggested_filename
            text.save_as(text_path)
            fixed = text_path.read_text(encoding="utf-8")
            assert fixed == page.locator("#fixList").inner_text()
            lines = fixed.splitlines()
            assert len(lines) == 5
            assert all(line.startswith(f"[{number}] ") for number, line in enumerate(lines, 1))
            assert errors == [], errors
            print("PASS: Markdown and TXT saved; full report and reference numbers preserved")
            print(f"Downloads: {output_dir.resolve()}")
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=Path("build/site-dist"))
    parser.add_argument("--output-dir", type=Path, required=True, help="New download directory")
    args = parser.parse_args()
    verify_downloads(args.site_dir, args.output_dir)


if __name__ == "__main__":
    main()
