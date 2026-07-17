"""Deterministic static-versus-rendered browser fixture."""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from html2md.markdown.converter import html_to_markdown


class JavaScriptFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"""<!doctype html><html><body>
        <h1>Fixture</h1><div id="app">Static placeholder</div>
        <script>
        document.querySelector('#app').innerHTML =
          '<h2>Rendered content</h2><p>Created by JavaScript.</p>';
        </script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def test_static_and_browser_modes_have_deterministic_distinct_output():
    if os.getenv("HTML2MD_RUN_RENDER_E2E") != "1":
        pytest.skip("set HTML2MD_RUN_RENDER_E2E=1 with the render extra and Chromium")

    server = ThreadingHTTPServer(("127.0.0.1", 0), JavaScriptFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/fixture"
    try:
        static = html_to_markdown(url, trim=False)
        rendered = html_to_markdown(url, trim=False, render_js=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert static is not None and rendered is not None
    assert "Static placeholder" in static
    assert "Created by JavaScript" not in static
    assert "## Rendered content" in rendered
    assert "Created by JavaScript" in rendered
    assert "Static placeholder" not in rendered
