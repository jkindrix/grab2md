"""Output-contract tests for URL canonicalization and document metadata."""

from grab2md.markdown.converter import html_content_to_markdown
from grab2md.markdown.document import prepare_document

REMOTE_HTML = """
<!doctype html>
<html lang="en-US">
<head>
  <base href="/docs/v2/">
  <title>Fallback title</title>
  <meta property="og:title" content="Canonical Guide">
  <meta name="author" content="Ada Example">
  <meta property="article:published_time" content="2026-07-16T10:30:00Z">
  <meta name="description" content="A concise guide: with punctuation.">
  <link rel="canonical alternate" href="../guide?view=full">
</head>
<body>
  <h1>Guide</h1>
  <a href="chapter/one#start">Chapter</a>
  <a href="#local">Anchor</a>
  <a href="mailto:ada@example.com">Mail</a>
  <img src="../images/cover.png" srcset="small.png 1x, /large.png 2x" alt="Cover">
</body>
</html>
"""


def test_remote_references_use_document_base_and_preserve_non_web_links():
    prepared, metadata = prepare_document(
        REMOTE_HTML, "https://example.com/original/page"
    )

    assert 'href="https://example.com/docs/v2/chapter/one#start"' in prepared
    assert 'href="#local"' in prepared
    assert 'href="mailto:ada@example.com"' in prepared
    assert 'src="https://example.com/docs/images/cover.png"' in prepared
    assert (
        'srcset="https://example.com/docs/v2/small.png 1x, '
        'https://example.com/large.png 2x"' in prepared
    )
    assert metadata.canonical_url == "https://example.com/docs/guide?view=full"


def test_metadata_front_matter_has_fixed_order_and_yaml_safe_values():
    markdown = html_content_to_markdown(
        REMOTE_HTML,
        "https://example.com/original/page",
        include_metadata=True,
    )

    assert markdown is not None
    expected = """---
title: "Canonical Guide"
author: "Ada Example"
date: "2026-07-16T10:30:00Z"
canonical_url: "https://example.com/docs/guide?view=full"
description: "A concise guide: with punctuation."
language: "en-US"
---

"""
    assert markdown.startswith(expected)
    assert "[Chapter](https://example.com/docs/v2/chapter/one#start)" in markdown
    assert "![Cover](https://example.com/docs/images/cover.png)" in markdown


def test_metadata_is_opt_in_but_remote_canonicalization_is_default():
    markdown = html_content_to_markdown(
        REMOTE_HTML, "https://example.com/original/page"
    )

    assert markdown is not None
    assert not markdown.startswith("---")
    assert "[Chapter](https://example.com/docs/v2/chapter/one#start)" in markdown


def test_local_references_remain_relative_and_metadata_can_be_preserved():
    html = """
    <html lang="fr"><head><title>Local Guide</title>
    <meta name="author" content="Local Author"></head>
    <body><a href="chapter.html">Chapter</a><img src="image.png" alt="Image"></body></html>
    """

    markdown = html_content_to_markdown(
        html, "file:///tmp/docs/page.html", include_metadata=True
    )

    assert markdown is not None
    assert 'title: "Local Guide"' in markdown
    assert 'author: "Local Author"' in markdown
    assert "canonical_url:" not in markdown
    assert "[Chapter](chapter.html)" in markdown
    assert "![Image](image.png)" in markdown


def test_remote_document_without_canonical_uses_final_source_url():
    _, metadata = prepare_document(
        "<html><head><title>Page</title></head></html>",
        "https://example.com/final",
    )

    assert metadata.canonical_url == "https://example.com/final"
