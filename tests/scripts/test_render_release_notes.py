from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "render_release_notes.py"


def _run(
    changelog: Path,
    version: str,
    artifacts: list[Path],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--changelog",
            str(changelog),
            "--version",
            version,
            *(str(path) for path in artifacts),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def _release_files(tmp_path: Path) -> tuple[Path, Path]:
    wheel = tmp_path / "grab2md-1.2.3-py3-none-any.whl"
    sdist = tmp_path / "grab2md-1.2.3.tar.gz"
    wheel.write_bytes(b"wheel bytes")
    sdist.write_bytes(b"source bytes")
    return wheel, sdist


def test_renders_dated_section_and_stable_artifact_checksums(
    tmp_path: Path,
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """\
## [Unreleased]

## [1.2.3] - 2026-07-24

### Fixed

- Kept the release evidence reproducible.

## [1.2.2] - 2026-07-23

- Older work.
""",
        encoding="utf-8",
    )
    wheel, sdist = _release_files(tmp_path)

    result = _run(changelog, "1.2.3", [sdist, wheel])

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("## [1.2.3] - 2026-07-24\n")
    assert "## [1.2.2]" not in result.stdout
    wheel_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
    sdist_hash = hashlib.sha256(sdist.read_bytes()).hexdigest()
    assert result.stdout.endswith(
        "### Distribution checksums\n\n"
        "```text\n"
        f"{wheel_hash}  {wheel.name}\n"
        f"{sdist_hash}  {sdist.name}\n"
        "```\n"
    )


def test_rejects_missing_or_duplicate_dated_section(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    wheel, sdist = _release_files(tmp_path)
    changelog.write_text("## [Unreleased]\n", encoding="utf-8")

    missing = _run(changelog, "1.2.3", [wheel, sdist])

    assert missing.returncode == 2
    assert "exactly one dated CHANGELOG section for 1.2.3, found 0" in missing.stderr

    changelog.write_text(
        "## [1.2.3] - 2026-07-24\n\n## [1.2.3] - 2026-07-25\n",
        encoding="utf-8",
    )
    duplicate = _run(changelog, "1.2.3", [wheel, sdist])

    assert duplicate.returncode == 2
    assert "exactly one dated CHANGELOG section for 1.2.3, found 2" in duplicate.stderr


def test_rejects_incomplete_or_mismatched_artifact_set(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [1.2.3] - 2026-07-24\n", encoding="utf-8")
    wheel, sdist = _release_files(tmp_path)

    incomplete = _run(changelog, "1.2.3", [wheel])

    assert incomplete.returncode == 2
    assert "exactly one wheel and one source distribution" in incomplete.stderr

    mismatched = tmp_path / "grab2md-1.2.4.tar.gz"
    mismatched.write_bytes(sdist.read_bytes())
    wrong_version = _run(changelog, "1.2.3", [wheel, mismatched])

    assert wrong_version.returncode == 2
    assert "grab2md-1.2.3.tar.gz" in wrong_version.stderr
