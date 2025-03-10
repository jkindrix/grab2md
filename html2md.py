#!/usr/bin/env python3

import requests
from markdownify import markdownify as md
import argparse
import re
import sys
from urllib.parse import urlparse
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def find_nth_occurrence(text, substring, n):
    """Find the nth occurrence of a substring in a string."""
    index = -1
    for _ in range(n):
        index = text.find(substring, index + 1)
        if index == -1:
            return -1  # Return -1 if the nth occurrence is not found
    return index

# Additional function to improve Markdown formatting
def format_markdown(markdown_content):
    # Remove "" link symbols (Unicode character for link symbol)
    formatted_content = re.sub(r'', '', markdown_content)
    
    # Fix heading links to wrap them properly
    formatted_content = re.sub(r'(#{1,6} )([^\[]+)\[\]\((#[^\)]+)\)', r'\1[\2](\3)', formatted_content)

    # Ensure code blocks are fenced properly (if not already handled by markdownify)
    formatted_content = formatted_content.replace('<pre><code>', '```\n').replace('</code></pre>', '\n```')
    
    # Remove extra newlines (more than two consecutive newlines)
    formatted_content = re.sub(r'\n{3,}', '\n\n', formatted_content)
    
    return formatted_content

from urllib.parse import urlparse

def trim_markdown(markdown_content, url):
    """Trim content before the first H1 and after the license text based on domain and URL path."""
    
    # Extract domain and path from the URL
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    path = parsed_url.path

    # Find the first H1 header
    h1_index = markdown_content.find('# ')

    # Initialize footer_index to avoid "UnboundLocalError"
    footer_index = -1

    # Different behavior based on the domain and path
    if "docs.datadoghq.com" in domain:
        footer_index = markdown_content.find('## Further reading')
    
    elif "learn.microsoft.com" in domain:
        footer_index = markdown_content.find('## See Also')
    
    
    elif "developer.android.com" in domain:
        footer_index = markdown_content.find('Content and code samples on this page are subject to the licenses described in the')
    
    elif "developer.hashicorp.com" in domain:
        if path.startswith("/vault/tutorials"):
            # Tutorials: Use 2nd H1 occurrence and trim at "Was this tutorial helpful?"
            h1_index = find_nth_occurrence(markdown_content, '# ', 2)
            footer_index = markdown_content.find('**Was this tutorial helpful?**')
        elif path.startswith(("/vault/docs", "/vault/api-docs")):
            # Docs & API Docs: Use 3rd H1 occurrence and trim at "Edit this page on GitHub"
            h1_index = find_nth_occurrence(markdown_content, '# ', 3)
            footer_index = markdown_content.find('[Edit this page on GitHub]')

    elif "hashicorp.com" in domain:
        footer_index = markdown_content.find("#### Sign up for the latest HashiCorp news")

    # Log values after ensuring footer_index is always defined
    logging.info(f"URL: {url}")
    logging.info(f"Path: {path}")
    logging.info(f"H1 index found: {h1_index}")
    logging.info(f"Footer index found: {footer_index}")

    # If both are found, trim the content
    if h1_index != -1 and footer_index != -1:
        logging.info("Both H1 and footer indexes found, trimming content.")
        return markdown_content[h1_index:footer_index].strip()
    
    logging.info("Failed to find either H1 index or footer index, returning full content.")
    return markdown_content


# Function to fetch HTML content and convert to markdown
def html_to_markdown(url, trim=False):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0'
    }
    
    # Fetch the HTML content from the URL
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:  # Check if the request was successful
        html_content = response.text
        
        # Convert HTML to Markdown with appropriate configuration for headers
        markdown_content = md(html_content, heading_style='ATX')  # ATX-style headers (e.g., # for h1)
        
        # Apply additional formatting to the markdown content
        formatted_markdown = format_markdown(markdown_content)
        
        # Trim content if the flag is set
        if trim:
            formatted_markdown = trim_markdown(formatted_markdown, url)
        
        return formatted_markdown
    else:
        print(f"Failed to retrieve the page at {url}. Status code: {response.status_code}", file=sys.stderr)
        return None


# Main function to handle command-line arguments
def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Convert HTML content from URLs to Markdown.')
    
    # Define arguments
    parser.add_argument('urls', nargs='+', help='The URLs of the HTML pages to convert, separated by whitespace.')
    parser.add_argument('--trim', action='store_true', help='Trim content before the first H1 header and after the license line.')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Combine all input into a single string and split by whitespace and newlines to handle multi-line input
    urls = ' '.join(args.urls).split()
    
    # Process each URL and concatenate results
    for url in urls:
        markdown_result = html_to_markdown(url, trim=args.trim)
        if markdown_result:
            # Add URL header at the top of each result
            print(f"\n# URL: {url}\n")
            print(markdown_result)

# Run the script
if __name__ == "__main__":
    main()
