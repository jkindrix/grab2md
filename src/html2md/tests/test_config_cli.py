"""Command-level tests for schema-backed CLI defaults."""

from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from html2md.cli.cli import DEFAULT_CONFIG, app


runner = CliRunner()


@pytest.mark.parametrize(
    "command, option, raw, expected",
    [
        ("convert", "trim", "false", False),
        ("crawl", "max_pages", "250", 250),
        ("crawl", "delay", "1.5", 1.5),
        ("crawl", "rate_limit", "30", 30),
        ("crawl", "rate_limit", "null", None),
        ("convert", "browser", "firefox", "firefox"),
        ("convert", "images_dir", "page-assets", "page-assets"),
    ],
)
def test_set_cli_default_parses_and_saves_schema_type(command, option, raw, expected):
    config = deepcopy(DEFAULT_CONFIG)
    save = Mock()

    with (
        patch("html2md.cli.cli.load_config", return_value=config),
        patch("html2md.cli.cli.save_config", save),
    ):
        result = runner.invoke(
            app, ["config", "set-cli-default", command, option, raw]
        )

    assert result.exit_code == 0
    saved = save.call_args.args[0]
    assert saved["cli_defaults"][command][option] == expected
    assert type(saved["cli_defaults"][command][option]) is type(expected)


def test_set_cli_default_reset_restores_builtin_value():
    config = deepcopy(DEFAULT_CONFIG)
    config["cli_defaults"]["crawl"]["max_pages"] = 999
    save = Mock()

    with (
        patch("html2md.cli.cli.load_config", return_value=config),
        patch("html2md.cli.cli.save_config", save),
    ):
        result = runner.invoke(
            app, ["config", "set-cli-default", "crawl", "max_pages", "--reset"]
        )

    assert result.exit_code == 0
    assert save.call_args.args[0]["cli_defaults"]["crawl"]["max_pages"] == 100


@pytest.mark.parametrize(
    "arguments",
    [
        ["convert", "trim", "sometimes"],
        ["crawl", "max_pages", "1.5"],
        ["crawl", "rate_limit", "fast"],
        ["convert", "browser", "opera"],
        ["crawl", "missing", "1"],
        ["missing", "trim", "true"],
        ["crawl", "max_pages"],
        ["crawl", "max_pages", "10", "--reset"],
    ],
)
def test_set_cli_default_rejects_invalid_input_without_saving(arguments):
    save = Mock()
    with (
        patch("html2md.cli.cli.load_config", return_value=deepcopy(DEFAULT_CONFIG)),
        patch("html2md.cli.cli.save_config", save),
    ):
        result = runner.invoke(app, ["config", "set-cli-default", *arguments])

    assert result.exit_code == 1
    assert "Error" in result.output
    save.assert_not_called()
