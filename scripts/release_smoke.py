#!/usr/bin/env python3
"""Install one built wheel outside the checkout and exercise release contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import venv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<html><h1>Release fixture</h1><p>installed wheel</p></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        return


def run(
    command: list[str], *, cwd: Path, expected: int = 0
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"Command returned {result.returncode}, expected {expected}: {command}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--expected-version", required=True)
    arguments = parser.parse_args()
    wheel = arguments.wheel.resolve(strict=True)
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()

    with tempfile.TemporaryDirectory(prefix="html2md-release-smoke-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        command = scripts / ("html2md.exe" if os.name == "nt" else "html2md")
        run([str(python), "-m", "pip", "install", "--quiet", str(wheel)], cwd=root)

        assert (
            run([str(command), "--version"], cwd=root).stdout.strip()
            == arguments.expected_version
        )
        run([str(command), "--help"], cwd=root)
        run([str(python), "-I", "-m", "html2md", "--help"], cwd=root)

        source = root / "source.html"
        local_output = root / "local.md"
        source.write_text("<h1>Local fixture</h1>", encoding="utf-8")
        run(
            [
                str(command),
                "convert",
                str(source),
                "--local",
                "--output",
                str(local_output),
            ],
            cwd=root,
        )
        assert "# Local fixture" in local_output.read_text(encoding="utf-8")

        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            remote_output = root / "remote.md"
            run(
                [
                    str(command),
                    "convert",
                    f"http://127.0.0.1:{server.server_port}/page",
                    "--allow-private-network",
                    "--output",
                    str(remote_output),
                ],
                cwd=root,
            )
            assert "# Release fixture" in remote_output.read_text(encoding="utf-8")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        run(
            [str(command), "convert", str(root / "missing.html"), "--local"],
            cwd=root,
            expected=1,
        )

    print(
        json.dumps(
            {
                "wheel": wheel.name,
                "sha256": digest,
                "version": arguments.expected_version,
                "smokes": ["version", "help", "module", "local", "loopback", "failure"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
