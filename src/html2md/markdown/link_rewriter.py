"""Rewrite successfully archived web links to source-relative Markdown paths."""

import os
import re
from urllib.parse import urlsplit, urlunsplit


MARKDOWN_LINK = re.compile(
    r"(?P<prefix>(?<!\!)\[[^\]]*\]\(\s*)"
    r"(?P<destination><https?://[^>]+>|https?://[^\s)]+)"
    r"(?P<suffix>(?:\s+(?:\"[^\"]*\"|'[^']*'))?\))"
)


def rewrite_links(content, url_mapping, source_file):
    """Rewrite mapped HTTP(S) links relative to the containing Markdown file.

    Exact query-bearing URLs map to their own archived file. Fragments remain
    anchors on the local target. If only the query-free URL was archived, its
    original query is retained on the rewritten destination.
    """
    source_dir = os.path.dirname(os.path.abspath(os.fspath(source_file)))

    def replace(match):
        raw_destination = match.group("destination")
        destination = raw_destination[1:-1] if raw_destination.startswith("<") else raw_destination
        parts = urlsplit(destination)
        without_fragment = urlunsplit(parts._replace(fragment=""))
        without_query_or_fragment = urlunsplit(parts._replace(query="", fragment=""))

        target = url_mapping.get(destination)
        preserve_query = False
        if target is None:
            target = url_mapping.get(without_fragment)
        if target is None:
            target = url_mapping.get(without_query_or_fragment)
            preserve_query = target is not None and bool(parts.query)
        if target is None:
            return match.group(0)

        relative_path = os.path.relpath(os.fspath(target), source_dir).replace(os.sep, "/")
        if preserve_query:
            relative_path += f"?{parts.query}"
        if parts.fragment:
            relative_path += f"#{parts.fragment}"
        return f"{match.group('prefix')}{relative_path}{match.group('suffix')}"

    return MARKDOWN_LINK.sub(replace, content)
