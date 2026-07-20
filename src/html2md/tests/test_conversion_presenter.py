"""Behavior tests for interactive and plain one-source presenters."""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.progress import Progress

from html2md.cli.conversion_presenter import (
    process_single_quiet,
    process_single_with_progress,
)
from html2md.cli.conversion_service import ConversionResult
from html2md.markdown.content_extractor import ContentMode


def presenter_arguments(**changes):
    values = {
        "source": "https://example.com/page",
        "content_mode": ContentMode.FULL,
        "selector": None,
        "output": None,
        "no_cookies": True,
        "browser_cookies": False,
        "browser": None,
    }
    values.update(changes)
    return values


def test_quiet_presenter_writes_markdown_or_reports_typed_failure(tmp_path, capsys):
    output = tmp_path / "page.md"
    success = ConversionResult(
        "https://example.com/page",
        "https://example.com/page",
        "# converted",
        True,
    )
    failure = ConversionResult(
        "https://example.com/page",
        "https://example.com/page",
        None,
        True,
        error="offline",
    )
    with patch(
        "html2md.cli.conversion_presenter._convert_one",
        side_effect=[success, failure],
    ):
        assert process_single_quiet(**presenter_arguments(output=output)) is True
        assert process_single_quiet(**presenter_arguments()) is False

    assert output.read_text(encoding="utf-8") == "# converted"
    assert "offline" in capsys.readouterr().err


def test_fancy_presenter_requires_all_runtime_collaborators():
    with pytest.raises(ValueError, match="required"):
        process_single_with_progress(**presenter_arguments())


def test_fancy_presenter_renders_success_and_failure_without_masking_status():
    stream = StringIO()
    console = Console(file=stream, force_terminal=False)
    progress = Progress(console=console)
    task = progress.add_task("queued", total=1)
    success = ConversionResult("local.html", "local.html", "# local", False)
    failure = ConversionResult(
        "https://example.com",
        "https://example.com",
        None,
        True,
        error="conversion failed",
    )
    with patch(
        "html2md.cli.conversion_presenter._convert_one",
        side_effect=[success, failure],
    ):
        assert (
            process_single_with_progress(
                **presenter_arguments(source="local.html"),
                progress=progress,
                task_id=task,
                console=console,
            )
            is True
        )
        assert (
            process_single_with_progress(
                **presenter_arguments(),
                progress=progress,
                task_id=task,
                console=console,
            )
            is False
        )

    rendered = stream.getvalue()
    assert "# local" in rendered
    assert "conversion failed" in rendered
    assert progress.tasks[0].description.startswith("❌ Failed")
