"""Behavior tests for domain and local Markdown trimming."""

from unittest.mock import patch

from html2md.markdown.trimmer import trim_markdown, trim_markdown_local


def configured(rules):
    return patch(
        "html2md.markdown.trimmer.load_config", return_value={"domains": rules}
    )


def test_unknown_domain_returns_content_unchanged():
    content = "intro\n# Heading\nbody"
    with configured({}):
        assert trim_markdown(content, "https://example.com/docs") == content


def test_domain_rule_trims_from_heading_to_footer():
    content = "navigation\n# Guide\nbody\nCopyright 2026\nfooter"
    with configured({"example.com": {"footer_marker": "Copyright"}}):
        result = trim_markdown(content, "https://example.com/docs")

    assert result == "# Guide\nbody"


def test_domain_footer_supports_html_entity_marker():
    content = "# Guide\nbody\n© 2026"
    with configured({"example.com": {"footer_marker": "&copy;"}}):
        result = trim_markdown(content, "https://example.com/docs")

    assert result == "# Guide\nbody"


def test_matching_path_rule_selects_heading_occurrence_and_footer():
    content = "# Navigation\nlinks\n# Guide\nbody\nEND\nfooter"
    rules = {
        "example.com": {
            "path_rules": {"/docs": {"h1_occurrence": 2, "footer_marker": "END"}}
        }
    }
    with configured(rules):
        result = trim_markdown(content, "https://example.com/docs/page")

    assert result == "# Guide\nbody"


def test_domain_footer_fallback_applies_when_path_rules_do_not_match():
    content = "navigation\n# Guide\nbody\nDOMAIN FOOTER\nlinks"
    rules = {
        "example.com": {
            "footer_marker": "DOMAIN FOOTER",
            "path_rules": {"/api": {"footer_marker": "API FOOTER"}},
        }
    }
    with configured(rules):
        result = trim_markdown(content, "https://example.com/docs/page")

    assert result == "# Guide\nbody"


def test_missing_heading_preserves_full_content():
    content = "navigation and body"
    with configured({"example.com": {"footer_marker": "footer"}}):
        assert trim_markdown(content, "https://example.com/") == content


def test_local_trimmer_uses_earliest_known_footer():
    content = "navigation\n# Guide\nbody\n## References\nrefs\n## License\nlicense"

    assert trim_markdown_local(content, "guide.html") == "# Guide\nbody"


def test_local_trimmer_without_heading_returns_stripped_content():
    assert trim_markdown_local("  body only  ", "page.html") == "body only"
