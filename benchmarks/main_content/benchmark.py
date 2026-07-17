#!/usr/bin/env python3
"""Compare raw conversion with optional main-content extractors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from markdownify import markdownify

FIXTURES = Path(__file__).with_name("fixtures.json")


@dataclass(frozen=True)
class Engine:
    name: str
    convert: Callable[[str], str]


def _engines() -> list[Engine]:
    engines = [
        Engine("raw", lambda html: markdownify(html, heading_style="ATX")),
    ]
    try:
        from readability import Document

        engines.append(
            Engine(
                "readability",
                lambda html: markdownify(
                    Document(html).summary(), heading_style="ATX"
                ),
            )
        )
    except ImportError:
        pass

    try:
        from trafilatura import extract

        engines.append(
            Engine(
                "trafilatura",
                lambda html: extract(
                    html,
                    output_format="markdown",
                    include_comments=False,
                    include_images=True,
                    include_links=True,
                    include_tables=True,
                )
                or "",
            )
        )
    except ImportError:
        pass
    return engines


def _ratio(matches: int, total: int) -> str:
    return f"{matches / total:.0%}"


def main() -> None:
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    print("fixture\tengine\trequired_recall\tboilerplate_rejection\tcharacters")
    for fixture in fixtures:
        for engine in _engines():
            output = engine.convert(fixture["html"])
            retained = sum(marker in output for marker in fixture["required"])
            rejected = sum(marker not in output for marker in fixture["boilerplate"])
            print(
                f"{fixture['name']}\t{engine.name}\t"
                f"{_ratio(retained, len(fixture['required']))}\t"
                f"{_ratio(rejected, len(fixture['boilerplate']))}\t{len(output)}"
            )


if __name__ == "__main__":
    main()
