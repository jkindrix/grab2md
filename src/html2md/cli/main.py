import argparse
import glob
import logging
import os
from urllib.parse import urlparse

from html2md.cookies.session_manager import get_session
from html2md.markdown.batch_processor import process_markdown_links
from html2md.markdown.converter import html_to_markdown, local_html_to_markdown
from html2md.markdown.crawler import crawl_website
from html2md.utils.logger import setup_logging

logger = setup_logging()


def build_headers(url):
    """Dynamically construct request headers based on the target URL."""
    parsed_url = urlparse(url)
    domain = parsed_url.netloc

    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://{domain}/",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


def save_to_file(output_filename, content):
    """Save the converted markdown content to a file."""
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved output to {output_filename}")
    except IOError as e:
        logger.error(f"Failed to write to {output_filename}: {e}")


def is_url(source, force_local=False):
    """Determine if the source is a URL or a local file path."""
    if force_local:
        return False

    parsed = urlparse(source)
    return bool(parsed.scheme in ("http", "https") and parsed.netloc)


def process_single(source, trim=True, output=None, no_cookies=False, local=False):
    """Process a single URL or file and save/print the result."""
    if is_url(source, local):
        # Process as URL
        headers = build_headers(source)
        logger.info(f"Processing URL: {source}")

        try:
            # Create a new session for each URL if cookies are not disabled
            session = get_session() if not no_cookies else None

            # Process URL with session and headers
            markdown_result = html_to_markdown(
                source, session=session, headers=headers, trim=trim
            )

            if markdown_result:
                if output:
                    save_to_file(output, markdown_result)
                else:
                    print(f"\n# URL: {source}\n")
                    print(markdown_result)
                logger.info(f"Successfully processed URL: {source}")
                return True
        except Exception as e:
            logger.error(f"Failed to process URL {source}: {e}")
            return False
    else:
        # Process as local file
        logger.info(f"Processing local file: {source}")

        try:
            # Expand to absolute path if needed
            file_path = os.path.abspath(os.path.expanduser(source))

            # Process local file
            markdown_result = local_html_to_markdown(file_path, trim=trim)

            if markdown_result:
                if output:
                    save_to_file(output, markdown_result)
                else:
                    print(f"\n# File: {file_path}\n")
                    print(markdown_result)
                logger.info(f"Successfully processed local file: {file_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to process local file {source}: {e}")
            return False

    return False


def process_batch(input_files, output_dir, trim=True, flatten_output=False):
    """Process a batch of markdown files with links to convert."""
    # Expand any glob patterns in input files
    expanded_files = []
    for pattern in input_files:
        matches = glob.glob(os.path.expanduser(pattern))
        if matches:
            expanded_files.extend(matches)
        else:
            logger.warning(f"No files found matching pattern: {pattern}")

    if not expanded_files:
        logger.error("No input files found to process.")
        return False

    # Process the files
    try:
        processed_count = process_markdown_links(
            expanded_files, output_dir, trim, flatten_output=flatten_output
        )
        logger.info(f"Batch processing complete. Processed {processed_count} URLs.")
        return processed_count > 0
    except Exception as e:
        logger.error(f"Error during batch processing: {e}")
        return False


def process_recursive(
    start_urls,
    output_dir,
    follow_option="domain-only",
    max_depth=3,
    max_pages=100,
    trim=True,
    flatten_output=False,
):
    """Process URLs recursively, following links according to the follow option."""
    total_processed = 0

    for start_url in start_urls:
        if not is_url(start_url):
            logger.error(f"Invalid URL: {start_url}")
            continue

        try:
            logger.info(f"Starting recursive crawl from: {start_url}")
            processed_count, _ = crawl_website(
                start_url,
                output_dir,
                follow_option=follow_option,
                max_depth=max_depth,
                max_pages=max_pages,
                trim=trim,
                flatten_output=flatten_output,
            )
            total_processed += processed_count
            logger.info(
                f"Crawling complete for {start_url}. Processed {processed_count} pages."
            )
        except Exception as e:
            logger.error(f"Error during recursive processing of {start_url}: {e}")

    logger.info(
        f"Recursive processing complete. Total processed: {total_processed} pages."
    )
    return total_processed > 0


def main():
    """Parse arguments and process URLs or local files."""
    parser = argparse.ArgumentParser(
        description="Convert HTML content from URLs or local files to Markdown."
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Single file/URL conversion (default)
    single_parser = subparsers.add_parser(
        "convert", help="Convert a single URL or file to markdown"
    )
    single_parser.add_argument(
        "sources", nargs="+", help="URLs or local HTML files to convert."
    )
    single_parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )
    single_parser.add_argument(
        "--output",
        type=str,
        help="Specify output file to save converted markdown. If not provided, prints to stdout.",
    )
    single_parser.add_argument(
        "--no-cookies",
        action="store_true",
        help="Disable loading cookies from the browser.",
    )
    single_parser.add_argument(
        "--local",
        action="store_true",
        help="Force treating sources as local files even if they look like URLs.",
    )

    # Batch processing
    batch_parser = subparsers.add_parser(
        "batch", help="Process markdown files with links and create modular output"
    )
    batch_parser.add_argument(
        "input_files", nargs="+", help="Markdown files containing links to process."
    )
    batch_parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to save the output files and folders. Default is 'output'.",
    )
    batch_parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )
    batch_parser.add_argument(
        "--flatten",
        action="store_true",
        dest="flatten_output",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    )

    # Recursive crawling
    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Recursively crawl websites from starting URLs and convert to markdown",
    )
    crawl_parser.add_argument("start_urls", nargs="+", help="Starting URLs to crawl.")
    crawl_parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Directory to save the output files and folders. Default is 'output'.",
    )
    crawl_parser.add_argument(
        "--follow",
        type=str,
        default="domain-only",
        help="How to follow links. Options: 'domain-only', 'host-only', 'subdomain', or a regex pattern.",
    )
    crawl_parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum link depth to follow. Default is 3.",
    )
    crawl_parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum number of pages to crawl. Default is 100.",
    )
    crawl_parser.add_argument(
        "--no-trim",
        action="store_false",
        dest="trim",
        help="Disable trimming based on domain-specific rules.",
    )
    crawl_parser.add_argument(
        "--flatten",
        action="store_true",
        dest="flatten_output",
        help="Output files directly to domain directories (e.g., 'docs.github.com/')",
    )

    # Common arguments
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level (default: INFO).",
    )

    args = parser.parse_args()

    # Set logging level dynamically
    logger.setLevel(getattr(logging, args.log_level.upper(), logging.INFO))

    # Default to 'convert' if no command is specified
    if not args.command:
        parser.print_help()
        return

    # Ensure trim is True by default
    if hasattr(args, "trim"):
        args.trim = True if args.trim is None else args.trim

    # Process based on command
    if args.command == "convert":
        for source in args.sources:
            process_single(
                source,
                trim=args.trim,
                output=args.output,
                no_cookies=args.no_cookies,
                local=args.local,
            )
    elif args.command == "batch":
        process_batch(
            args.input_files,
            args.output_dir,
            args.trim,
            flatten_output=getattr(args, "flatten_output", False),
        )
    elif args.command == "crawl":
        process_recursive(
            args.start_urls,
            args.output_dir,
            follow_option=args.follow,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            trim=args.trim,
            flatten_output=args.flatten_output,
        )


if __name__ == "__main__":
    main()
