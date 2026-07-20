"""Regression evidence that account-password authentication is not shipped."""

import inspect
from pathlib import Path

import pytest
from typer.testing import CliRunner

from html2md.cli.cli import app
from html2md.markdown.converter import html_to_markdown

runner = CliRunner()


def test_converter_api_has_no_account_credential_parameters():
    parameters = inspect.signature(html_to_markdown).parameters

    assert "oauth_email" not in parameters
    assert "oauth_password" not in parameters
    with pytest.raises(TypeError, match="oauth_password"):
        html_to_markdown("https://example.com", oauth_password="must-not-be-accepted")


def test_convert_cli_exposes_no_account_credential_options():
    result = runner.invoke(app, ["convert", "--help"])

    assert result.exit_code == 0
    assert "oauth-email" not in result.output.lower()
    assert "oauth-password" not in result.output.lower()


def test_production_tree_contains_no_private_password_flow():
    package_root = Path(__file__).parents[1]
    production_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package_root.rglob("*.py")
        if "tests" not in path.parts
    ).lower()

    assert "oauth_password" not in production_text
    assert "/api/auth/signin/email" not in production_text
