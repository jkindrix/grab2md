"""Command-level tests for schema-backed CLI defaults."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from html2md.cli.cli import app
from html2md.config.loader import DEFAULT_CONFIG


runner = CliRunner()


def test_config_help_exposes_supported_command_surface():
    result = runner.invoke(app, ["config", "--help"])

    assert result.exit_code == 0
    for command in (
        "show",
        "path",
        "set",
        "get",
        "delete",
        "add-domain",
        "list-domains",
        "reset",
        "set-cli-default",
        "list-cli-defaults",
        "show-options",
        "backup",
        "list-backups",
        "restore",
    ):
        assert command in result.output


def test_config_show_renders_loaded_configuration():
    with patch(
        "html2md.cli.config_commands.load_config",
        return_value={"browser": {"preferred": "firefox"}},
    ):
        result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "Configuration file" in result.output
    assert "firefox" in result.output


def test_config_set_updates_nested_value():
    config = {"browser": {"preferred": "chrome"}}
    save = Mock()
    with (
        patch("html2md.cli.config_commands.load_config", return_value=config),
        patch("html2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(
            app,
            ["config", "set", "browser.preferred", '"firefox"'],
        )

    assert result.exit_code == 0
    assert save.call_args.args[0]["browser"]["preferred"] == "firefox"


def test_config_add_domain_quick_persists_domain():
    config = {"domains": {}}
    save = Mock()
    with (
        patch("html2md.cli.config_commands.load_config", return_value=config),
        patch("html2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(
            app, ["config", "add-domain", "--domain", "example.com", "--quick"]
        )

    assert result.exit_code == 0
    assert save.call_args.args[0]["domains"]["example.com"] == {}


def test_config_backup_reports_created_path(tmp_path):
    manager = Mock()
    manager.create_backup.return_value = tmp_path / "config.backup.json"
    with patch(
        "html2md.cli.config_commands.get_backup_manager", return_value=manager
    ):
        result = runner.invoke(app, ["config", "backup"])

    assert result.exit_code == 0
    assert "Backup created" in result.output
    manager.create_backup.assert_called_once_with(reason="manual")


def test_config_restore_uses_explicit_backup(tmp_path):
    backup = tmp_path / "config.backup.json"
    backup.write_text("{}", encoding="utf-8")
    manager = Mock()
    manager.create_backup.return_value = Path("pre-restore.json")
    manager.restore_backup.return_value = True
    with patch(
        "html2md.cli.config_commands.get_backup_manager", return_value=manager
    ):
        result = runner.invoke(
            app, ["config", "restore", str(backup)], input="y\n"
        )

    assert result.exit_code == 0
    assert "restored successfully" in result.output
    manager.restore_backup.assert_called_once_with(backup)


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
        patch("html2md.cli.config_commands.load_config", return_value=config),
        patch("html2md.cli.config_commands.save_config", save),
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
        patch("html2md.cli.config_commands.load_config", return_value=config),
        patch("html2md.cli.config_commands.save_config", save),
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
        patch(
            "html2md.cli.config_commands.load_config",
            return_value=deepcopy(DEFAULT_CONFIG),
        ),
        patch("html2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(app, ["config", "set-cli-default", *arguments])

    assert result.exit_code == 1
    assert "Error" in result.output
    save.assert_not_called()
