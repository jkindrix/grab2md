import re

from grab2md.utils.redaction import get_redacting_logger

logger = get_redacting_logger(__name__)

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _collapse_prose_newlines(markdown_content: str) -> str:
    """Collapse excessive prose spacing without modifying fenced code."""
    output: list[str] = []
    prose: list[str] = []
    fence: tuple[str, int] | None = None

    def flush_prose() -> None:
        if prose:
            output.append(re.sub(r"\n{3,}", "\n\n", "".join(prose)))
            prose.clear()

    for line in markdown_content.splitlines(keepends=True):
        line_without_ending = line.rstrip("\r\n")
        if fence is not None:
            output.append(line)
            character, minimum_length = fence
            if re.fullmatch(
                rf" {{0,3}}{re.escape(character)}{{{minimum_length},}}[ \t]*",
                line_without_ending,
            ):
                fence = None
            continue

        opening = _FENCE_OPEN.match(line_without_ending)
        if opening:
            flush_prose()
            marker = opening.group(1)
            fence = (marker[0], len(marker))
            output.append(line)
        else:
            prose.append(line)

    flush_prose()
    return "".join(output)


def format_markdown(markdown_content):
    """
    Format Markdown for improved readability.

    Args:
        markdown_content (str): Raw markdown content.

    Returns:
        str: Formatted markdown content.
    """
    if not isinstance(markdown_content, str):
        raise ValueError("Expected markdown_content to be a string")

    logger.info("Applying markdown formatting...")

    # Fix improperly formatted headers with links
    markdown_content = re.sub(
        r"(#{1,6} )([^\[]+)\[\]\((#[^\)]+)\)", r"\1[\2](\3)", markdown_content
    )
    logger.info("Fixed markdown headers with links")

    # Convert <pre><code> blocks to Markdown-style code blocks
    markdown_content = markdown_content.replace("<pre><code>", "```\n").replace(
        "</code></pre>", "\n```"
    )
    logger.info("Converted HTML <pre><code> to markdown code blocks")

    # Collapse excessive prose newlines without altering authored code.
    markdown_content = _collapse_prose_newlines(markdown_content)
    logger.info("Collapsed excessive newlines")

    return markdown_content
