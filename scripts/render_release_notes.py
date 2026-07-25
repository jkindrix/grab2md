#!/usr/bin/env python3
"""Render deterministic release notes from the changelog and distributions."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

DATED_RELEASE_HEADING = re.compile(
    r"^## \[(?P<version>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})$"
)
VERSION_HEADING = re.compile(r"^## \[[^\]]+\](?: - \d{4}-\d{2}-\d{2})?$")


def changelog_section(changelog: str, version: str) -> str:
    """Return the one dated changelog section for ``version``."""
    lines = changelog.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if (match := DATED_RELEASE_HEADING.fullmatch(line))
        and match.group("version") == version
    ]
    if len(starts) != 1:
        raise ValueError(
            f"expected exactly one dated CHANGELOG section for {version}, "
            f"found {len(starts)}"
        )

    start = starts[0]
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if VERSION_HEADING.fullmatch(lines[index])
        ),
        len(lines),
    )
    section = "\n".join(lines[start:end]).rstrip()
    if not section:
        raise ValueError(f"CHANGELOG section for {version} is empty")
    return section


def release_artifacts(version: str, paths: list[Path]) -> tuple[Path, Path]:
    """Validate and return the wheel and source distribution in stable order."""
    if len(paths) != 2:
        raise ValueError(
            f"expected exactly one wheel and one source distribution, found {len(paths)}"
        )
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("release artifact paths must be distinct")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"release artifacts do not exist: {', '.join(missing)}")

    wheel_prefix = f"grab2md-{version}-"
    wheels = [
        path
        for path in paths
        if path.name.startswith(wheel_prefix) and path.name.endswith(".whl")
    ]
    expected_sdist = f"grab2md-{version}.tar.gz"
    sdists = [path for path in paths if path.name == expected_sdist]
    if len(wheels) != 1 or len(sdists) != 1:
        names = ", ".join(sorted(path.name for path in paths))
        raise ValueError(
            "artifacts must contain one "
            f"{wheel_prefix}*.whl and one {expected_sdist}; found: {names}"
        )
    return wheels[0], sdists[0]


def render_release_notes(
    changelog_path: Path,
    version: str,
    artifact_paths: list[Path],
) -> str:
    """Return release notes with checksums for the exact distribution pair."""
    section = changelog_section(
        changelog_path.read_text(encoding="utf-8"),
        version,
    )
    artifacts = release_artifacts(version, artifact_paths)
    checksum_lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in artifacts
    ]
    checksums = "\n".join(checksum_lines)
    return (
        f"{section}\n\n"
        "### Distribution checksums\n\n"
        "```text\n"
        f"{checksums}\n"
        "```\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render one dated CHANGELOG section and SHA-256 checksums for the "
            "exact wheel and source distribution."
        )
    )
    parser.add_argument("--version", required=True, help="Exact release version")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Changelog path (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "artifacts",
        type=Path,
        nargs="+",
        help="Exactly one grab2md wheel and one source distribution",
    )
    args = parser.parse_args()

    try:
        notes = render_release_notes(
            args.changelog,
            args.version,
            args.artifacts,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(notes, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
