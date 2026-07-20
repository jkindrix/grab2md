import unittest

import pytest

from grab2md.markdown.batch_processor import (
    BatchInputError,
    load_batch_input,
    process_markdown_links,
)
from grab2md.markdown.link_rewriter import rewrite_links
from grab2md.utils.parser import extract_urls_from_markdown


class TestBatchProcessor(unittest.TestCase):
    """Tests for the batch processor module."""

    def test_extract_urls_from_markdown(self):
        """Test extracting URLs from markdown."""
        markdown = """
        # Test Markdown

        [Link 1](https://example.com/page1)
        [Link 2](https://example.com/page2)
        [Link with query](https://example.com/page?query=value)

        Plain text without links.

        [Link with fragment](https://example.com/page#section)
        """

        expected_urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page?query=value",
            "https://example.com/page#section",
        ]

        urls = extract_urls_from_markdown(markdown)
        self.assertEqual(urls, expected_urls)

    def test_rewrite_links(self):
        """Test rewriting links in markdown content."""
        content = """
        # Test Content

        [Link 1](https://example.com/page1)
        [Link 2](https://example.org/page2)
        """

        url_mapping = {
            "https://example.com/page1": "/output/example.com/page1.md",
            "https://example.org/page2": "/output/example.org/page2.md",
        }

        source_file = "/output/source.md"

        expected_content = """
        # Test Content

        [Link 1](example.com/page1.md)
        [Link 2](example.org/page2.md)
        """

        result = rewrite_links(content, url_mapping, source_file)
        self.assertEqual(result, expected_content)


if __name__ == "__main__":
    unittest.main()


def test_missing_batch_input_is_not_reported_as_an_empty_valid_file(tmp_path):
    missing = tmp_path / "missing.md"

    with pytest.raises(BatchInputError, match="Could not read batch input"):
        load_batch_input(missing)

    result = process_markdown_links([missing], tmp_path / "output")
    assert result.items == []
    assert result.input_errors
    assert "Could not read batch input" in (result.error or "")


def test_valid_batch_input_without_urls_has_a_distinct_empty_result(tmp_path):
    source = tmp_path / "empty.md"
    source.write_text("# No links here\n", encoding="utf-8")

    result = process_markdown_links([source], tmp_path / "output")

    assert result.input_errors == []
    assert result.error == "No URLs were found in the batch inputs"


def test_non_utf8_batch_input_is_a_typed_failure(tmp_path):
    source = tmp_path / "invalid.md"
    source.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(BatchInputError, match="Could not read batch input"):
        load_batch_input(source)
