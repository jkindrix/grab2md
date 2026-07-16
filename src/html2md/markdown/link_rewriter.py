"""Rewrite successfully archived web links to source-relative Markdown paths."""

import os
import re
from pathlib import Path
from typing import Callable, Mapping, Optional, Union
from urllib.parse import urlsplit, urlunsplit


MARKDOWN_LINK = re.compile(
    r"(?P<prefix>(?<!\!)\[[^\]]*\]\(\s*)"
    r"(?P<destination><https?://[^>]+>|https?://[^\s)]+)"
    r"(?P<suffix>(?:\s+(?:\"[^\"]*\"|'[^']*'))?\))"
)

OutputPath = Union[str, os.PathLike]
ProgressCallback = Callable[[str, Optional[str], Optional[str]], None]


def rewrite_links(content, url_mapping, source_file):
    """Rewrite mapped HTTP(S) links relative to the containing Markdown file.

    Exact query-bearing URLs map to their own archived file. Fragments remain
    anchors on the local target. If only the query-free URL was archived, its
    original query is retained on the rewritten destination.
    """
    source_dir = os.path.dirname(os.path.abspath(os.fspath(source_file)))

    def replace(match):
        raw_destination = match.group("destination")
        destination = (
            raw_destination[1:-1]
            if raw_destination.startswith("<")
            else raw_destination
        )
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

        relative_path = os.path.relpath(os.fspath(target), source_dir).replace(
            os.sep, "/"
        )
        if preserve_query:
            relative_path += f"?{parts.query}"
        if parts.fragment:
            relative_path += f"#{parts.fragment}"
        return f"{match.group('prefix')}{relative_path}{match.group('suffix')}"

    return MARKDOWN_LINK.sub(replace, content)


def rewrite_archived_files(
    url_mapping: Mapping[str, OutputPath],
    update_progress: ProgressCallback,
) -> int:
    """Rewrite every durable archived file, isolating per-file failures."""
    total = len(url_mapping)
    update_progress(f"Rewriting links between {total} files...", None, None)
    updated_count = 0

    for index, (url, output_file) in enumerate(url_mapping.items(), start=1):
        path = Path(output_file)
        update_progress(
            f"Updating links in file {index}/{total}: {path}",
            url,
            "updating",
        )
        try:
            content = path.read_text(encoding="utf-8")
            updated_content = rewrite_links(content, url_mapping, path)
            path.write_text(updated_content, encoding="utf-8")
            update_progress(f"Updated links in file: {path}", url, "updated")
            updated_count += 1
        except (OSError, UnicodeError) as error:
            update_progress(
                f"Error updating links in file {path}: {error}", url, "error"
            )

    return updated_count
