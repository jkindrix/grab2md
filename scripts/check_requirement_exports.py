#!/usr/bin/env python3
"""Fail when committed Poetry requirement exports drift from the lock."""

from __future__ import annotations

import argparse
import difflib
import subprocess
import tempfile
from pathlib import Path


def export(poetry: str, destination: Path, *, development: bool) -> None:
    command = [poetry, "export", "--without-hashes"]
    command.extend(["--with", "dev"] if development else ["--only", "main"])
    command.extend(["--format", "requirements.txt", "--output", str(destination)])
    subprocess.run(command, check=True, cwd=Path(__file__).resolve().parents[1])


def check(committed: Path, generated: Path) -> bool:
    expected = committed.read_text(encoding="utf-8").splitlines(keepends=True)
    actual = generated.read_text(encoding="utf-8").splitlines(keepends=True)
    if expected == actual:
        return True
    print(
        "".join(
            difflib.unified_diff(
                expected,
                actual,
                fromfile=str(committed),
                tofile=f"generated:{committed}",
            )
        ),
        end="",
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poetry", default="poetry")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="grab2md-requirements-") as raw:
        temporary = Path(raw)
        runtime = temporary / "requirements.txt"
        development = temporary / "requirements-dev.txt"
        export(arguments.poetry, runtime, development=False)
        export(arguments.poetry, development, development=True)
        clean = all(
            (
                check(root / "requirements.txt", runtime),
                check(root / "requirements-dev.txt", development),
            )
        )
    if clean:
        print("Committed requirement exports match poetry.lock.")
        return 0
    print("Regenerate requirement exports with the pinned Poetry toolchain.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
