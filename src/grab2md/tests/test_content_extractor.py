"""Content-selection contracts independent of fetching and presentation."""

from pathlib import Path

import pytest

from grab2md.markdown.content_extractor import (
    ContentExtractionError,
    ContentMode,
    extract_content_html,
    validate_content_request,
)

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "extraction"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["article.html", "documentation.html"])
def test_main_mode_prefers_one_semantic_region_without_page_furniture(name):
    extracted = extract_content_html(_fixture(name), mode=ContentMode.MAIN)

    assert "SHOULD NOT SURVIVE MAIN MODE" not in extracted
    assert "References are legitimate" in extracted or "license section" in extracted
    assert "<table>" in extracted
    assert "<code" in extracted


def test_main_mode_uses_readability_for_a_generic_article():
    extracted = extract_content_html(
        _fixture("generic-article.html"), mode=ContentMode.MAIN
    )

    assert "Generic Container Story" in extracted
    assert "evidence link" in extracted
    assert "MASTHEAD" not in extracted
    assert "FOOTER" not in extracted


def test_main_mode_fails_honestly_on_an_ambiguous_page():
    with pytest.raises(ContentExtractionError, match="No confident"):
        extract_content_html(_fixture("ambiguous.html"), mode=ContentMode.MAIN)


def test_full_mode_returns_input_byte_for_byte():
    html = _fixture("article.html")
    assert extract_content_html(html) == html


def test_selector_mode_supports_multiple_matches_and_rejects_no_match():
    html = "<div><p class='keep'>one</p><p>drop</p><p class='keep'>two</p></div>"

    extracted = extract_content_html(html, mode=ContentMode.SELECTOR, selector="p.keep")
    assert "one" in extracted and "two" in extracted and "drop" not in extracted

    with pytest.raises(ContentExtractionError, match="matched no content"):
        extract_content_html(html, mode=ContentMode.SELECTOR, selector="article")


def test_content_request_rejects_invalid_mode_selector_combinations():
    with pytest.raises(ContentExtractionError, match="requires --selector"):
        validate_content_request(ContentMode.SELECTOR, None)
    with pytest.raises(ContentExtractionError, match="--content selector"):
        validate_content_request(ContentMode.MAIN, ".article")
    with pytest.raises(ContentExtractionError, match="Invalid CSS selector"):
        extract_content_html("<main>body</main>", mode="selector", selector="[")


def test_main_mode_prunes_navigation_chrome_inside_the_region():
    body = "Genuine article body sentence. " * 12
    html = (
        "<html><body><main>"
        "<nav aria-label='Contents'>Jump to Alpha Deutsch Francais</nav>"
        f"<h1>Real Heading</h1><p>{body}</p>"
        "</main></body></html>"
    )
    extracted = extract_content_html(html, mode=ContentMode.MAIN)

    assert "Real Heading" in extracted
    assert "Genuine article body" in extracted
    assert "Jump to Alpha" not in extracted


def test_main_mode_selects_role_main_and_prunes_inner_navigation():
    body = "Reference documentation paragraph. " * 12
    html = (
        "<html><body>"
        "<div class='sphinxsidebar' role='navigation'>SIDEBAR NAV</div>"
        "<div class='body' role='main'>"
        "<div role='navigation'>ON THIS PAGE</div>"
        f"<h1>Documentation Title</h1><p>{body}</p>"
        "</div></body></html>"
    )
    extracted = extract_content_html(html, mode=ContentMode.MAIN)

    assert "Documentation Title" in extracted
    assert "Reference documentation paragraph" in extracted
    assert "SIDEBAR NAV" not in extracted  # outside role=main: never selected
    assert "ON THIS PAGE" not in extracted  # role=navigation inside: pruned


def test_main_mode_prunes_hidden_and_aria_hidden_within_region():
    body = "Visible content sentence here. " * 12
    html = (
        "<html><body><main>"
        "<span aria-hidden='true'>DECORATIVE ICON</span>"
        "<div hidden>COLLAPSED PANEL</div>"
        f"<h1>Kept Heading</h1><p>{body}</p>"
        "</main></body></html>"
    )
    extracted = extract_content_html(html, mode=ContentMode.MAIN)

    assert "Kept Heading" in extracted
    assert "DECORATIVE ICON" not in extracted
    assert "COLLAPSED PANEL" not in extracted


def test_main_mode_keeps_unpruned_region_when_pruning_would_empty_it():
    # A region that is almost entirely chrome must not be reduced to nothing;
    # the unpruned form is preferred over a near-empty result.
    nav_text = "Only navigation text here. " * 12
    html = f"<html><body><main><nav>{nav_text}</nav></main></body></html>"

    extracted = extract_content_html(html, mode=ContentMode.MAIN)

    assert "Only navigation text here" in extracted
