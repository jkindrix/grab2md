"""Conservative HTML-region selection before Markdown conversion."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from bs4 import BeautifulSoup, Tag
from readability import Document
from soupsieve import SelectorSyntaxError


class ContentMode(str, Enum):
    """Supported content-selection contracts."""

    FULL = "full"
    MAIN = "main"
    SELECTOR = "selector"


class ContentExtractionError(ValueError):
    """Raised when an explicitly requested region cannot be selected safely."""


def validate_content_request(
    mode: ContentMode | str, selector: Optional[str]
) -> ContentMode:
    """Normalize and validate a public content-selection request."""
    normalized = mode if isinstance(mode, ContentMode) else ContentMode(mode)
    if normalized is ContentMode.SELECTOR and not (selector and selector.strip()):
        raise ContentExtractionError("Selector mode requires --selector.")
    if normalized is not ContentMode.SELECTOR and selector:
        raise ContentExtractionError(
            "--selector requires '--content selector'; full and main modes do not use it."
        )
    return normalized


def _substantial_text(element: Tag) -> bool:
    return len(element.get_text(" ", strip=True)) >= 200


# Structural chrome that is never primary content and is pruned from an
# already-selected main region. Content-bearing wrappers (``header``/``footer``
# can carry a title or byline) are deliberately excluded from this list.
_BOILERPLATE_TAGS = ("nav", "aside", "script", "style", "noscript", "template")
# ARIA roles that mark structural chrome rather than primary content, plus
# explicitly hidden elements. ``~=`` matches whitespace-separated role tokens,
# so an element carrying several roles is still recognized.
_BOILERPLATE_SELECTOR = (
    '[role~="navigation"], [role~="complementary"], [role~="banner"], '
    '[role~="contentinfo"], [role~="search"], [aria-hidden="true"], [hidden]'
)


def _prune_boilerplate(region: Tag) -> None:
    """Remove structural chrome from a selected main region, in place."""
    removals: list[Tag] = list(region.find_all(_BOILERPLATE_TAGS))
    removals.extend(region.select(_BOILERPLATE_SELECTOR))
    for element in removals:
        if not element.decomposed:
            element.decompose()


def _select_main_region(soup: BeautifulSoup) -> Optional[Tag]:
    """Return the single unambiguous main region, or ``None`` when undecided."""
    articles = [
        element for element in soup.find_all("article") if _substantial_text(element)
    ]
    if len(articles) == 1:
        return articles[0]
    # A lone ``<main>`` element is authoritative; failing that, a single
    # ``role="main"`` container (used by many documentation generators that
    # never emit ``<main>``) is treated the same way.
    mains = soup.find_all("main")
    if len(mains) == 1:
        return mains[0]
    role_mains = soup.select('[role~="main"]')
    if len(role_mains) == 1:
        return role_mains[0]
    return None


def _semantic_main(soup: BeautifulSoup) -> Optional[str]:
    region = _select_main_region(soup)
    if region is None:
        return None
    # Prune on a detached copy so a shared soup (reused by selector mode) is
    # never mutated.
    region_copy = BeautifulSoup(str(region), "html.parser")
    _prune_boilerplate(region_copy)
    # Pruning must only ever help: if it drops a substantial region below the
    # selection bar (a region that was almost entirely chrome), keep the
    # unpruned form rather than returning a near-empty result.
    if len(region_copy.get_text(" ", strip=True)) >= 200:
        return str(region_copy)
    return str(region)


def _readability_main(html_content: str) -> str:
    try:
        extracted = Document(html_content).summary(html_partial=True)
    except Exception as error:
        raise ContentExtractionError(
            f"Main-content extraction failed: {error}"
        ) from error
    soup = BeautifulSoup(extracted, "html.parser")
    text_length = len(soup.get_text(" ", strip=True))
    if text_length < 300 or len(soup.find_all("p")) < 2:
        raise ContentExtractionError(
            "No confident main-content region was found; use '--content full' or "
            "'--content selector --selector <css>'."
        )
    return extracted


def extract_content_html(
    html_content: str,
    *,
    mode: ContentMode | str = ContentMode.FULL,
    selector: Optional[str] = None,
) -> str:
    """Return the requested HTML region without silently changing modes."""
    normalized = validate_content_request(mode, selector)
    if normalized is ContentMode.FULL:
        return html_content

    soup = BeautifulSoup(html_content, "html.parser")
    if normalized is ContentMode.MAIN:
        return _semantic_main(soup) or _readability_main(html_content)

    assert selector is not None  # established by validate_content_request
    try:
        selected = soup.select(selector)
    except SelectorSyntaxError as error:
        raise ContentExtractionError(f"Invalid CSS selector: {error}") from error
    if not selected:
        raise ContentExtractionError(f"CSS selector matched no content: {selector}")
    return "<main>" + "".join(str(element) for element in selected) + "</main>"
