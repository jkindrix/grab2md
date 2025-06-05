"""Image downloading functionality for html2md."""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, unquote
import requests
from requests import Session
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, TaskID

import logging

logger = logging.getLogger("html2md")
from ..errors import Html2MdError

console = Console()


class ImageDownloader:
    """Handles downloading and organizing images from web pages."""
    
    SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp'}
    MAX_FILENAME_LENGTH = 200
    
    def __init__(self, session: Optional[Session] = None, images_dir: str = "images"):
        """Initialize the image downloader.
        
        Args:
            session: Requests session to use for downloads
            images_dir: Directory name for storing images (relative to output)
        """
        self.session = session or requests.Session()
        self.images_dir = images_dir
        self.downloaded_images: Dict[str, str] = {}  # Map original URL to local path
        
    def extract_image_urls(self, html_content: str, base_url: str) -> List[str]:
        """Extract all image URLs from HTML content.
        
        Args:
            html_content: HTML content to parse
            base_url: Base URL for resolving relative links
            
        Returns:
            List of absolute image URLs
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        image_urls = []
        
        # Find all img tags
        for img in soup.find_all('img'):
            src = img.get('src', '').strip()
            if src:
                absolute_url = urljoin(base_url, src)
                image_urls.append(absolute_url)
                
            # Also check srcset for responsive images
            srcset = img.get('srcset', '')
            if srcset:
                # Parse srcset format: "url1 1x, url2 2x"
                for part in srcset.split(','):
                    url_part = part.strip().split()[0] if part.strip() else ''
                    if url_part:
                        absolute_url = urljoin(base_url, url_part)
                        image_urls.append(absolute_url)
        
        # Find images in CSS background-image properties
        style_pattern = re.compile(r'background-image:\s*url\(["\']?([^"\'()]+)["\']?\)', re.IGNORECASE)
        for element in soup.find_all(style=True):
            style = element.get('style', '')
            for match in style_pattern.finditer(style):
                url = match.group(1)
                absolute_url = urljoin(base_url, url)
                image_urls.append(absolute_url)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in image_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
                
        return unique_urls
    
    def _generate_filename(self, url: str, content_type: Optional[str] = None) -> str:
        """Generate a safe filename from URL and content type.
        
        Args:
            url: Image URL
            content_type: Content-Type header value
            
        Returns:
            Safe filename for the image
        """
        # Parse URL
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        # Extract filename from path
        filename = os.path.basename(path)
        
        # If no filename or it's just an extension, use domain + path hash
        if not filename or filename.startswith('.'):
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            filename = f"{parsed.netloc}_{url_hash}"
        
        # Ensure proper extension
        name, ext = os.path.splitext(filename)
        
        # Try to determine extension from content type if not present
        if not ext and content_type:
            mime_to_ext = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'image/svg+xml': '.svg',
                'image/x-icon': '.ico',
                'image/bmp': '.bmp'
            }
            ext = mime_to_ext.get(content_type.split(';')[0].strip(), '')
        
        # Default to .jpg if no extension
        if not ext:
            ext = '.jpg'
            
        # Ensure extension is supported
        if ext.lower() not in self.SUPPORTED_EXTENSIONS:
            ext = '.jpg'
            
        # Combine and sanitize
        filename = name + ext
        filename = re.sub(r'[^\w\-_\.]', '_', filename)
        
        # Truncate if too long
        if len(filename) > self.MAX_FILENAME_LENGTH:
            name, ext = os.path.splitext(filename)
            max_name_length = self.MAX_FILENAME_LENGTH - len(ext)
            filename = name[:max_name_length] + ext
            
        return filename
    
    def download_image(self, url: str, output_dir: Path) -> Optional[Path]:
        """Download a single image.
        
        Args:
            url: Image URL to download
            output_dir: Directory to save the image
            
        Returns:
            Path to downloaded image or None if failed
        """
        try:
            # Skip if already downloaded
            if url in self.downloaded_images:
                return Path(self.downloaded_images[url])
                
            # Make request
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Get content type
            content_type = response.headers.get('Content-Type', '')
            
            # Generate filename
            filename = self._generate_filename(url, content_type)
            
            # Create images directory
            images_path = output_dir / self.images_dir
            images_path.mkdir(parents=True, exist_ok=True)
            
            # Handle filename conflicts
            file_path = images_path / filename
            counter = 1
            while file_path.exists():
                name, ext = os.path.splitext(filename)
                file_path = images_path / f"{name}_{counter}{ext}"
                counter += 1
            
            # Download and save
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Store mapping
            relative_path = f"{self.images_dir}/{file_path.name}"
            self.downloaded_images[url] = relative_path
            
            logger.debug(f"Downloaded image: {url} -> {relative_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to download image {url}: {str(e)}")
            return None
    
    def download_images(self, image_urls: List[str], output_dir: Path, 
                       progress: Optional[Progress] = None, 
                       task: Optional[TaskID] = None) -> Dict[str, str]:
        """Download multiple images.
        
        Args:
            image_urls: List of image URLs to download
            output_dir: Directory to save images
            progress: Optional progress bar
            task: Optional task ID for progress updates
            
        Returns:
            Mapping of original URLs to local paths
        """
        results = {}
        total = len(image_urls)
        
        for i, url in enumerate(image_urls):
            if progress and task:
                progress.update(task, advance=1, description=f"Downloading images... [{i+1}/{total}]")
                
            local_path = self.download_image(url, output_dir)
            if local_path:
                results[url] = str(local_path.relative_to(output_dir))
                
        return results
    
    def rewrite_image_urls(self, markdown_content: str, url_mapping: Dict[str, str]) -> str:
        """Rewrite image URLs in markdown to point to local files.
        
        Args:
            markdown_content: Markdown content with image references
            url_mapping: Mapping of original URLs to local paths
            
        Returns:
            Markdown content with rewritten image URLs
        """
        # Pattern for markdown images: ![alt](url)
        image_pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
        
        def replace_url(match):
            alt_text = match.group(1)
            url = match.group(2)
            
            # Check if we have a local version
            if url in url_mapping:
                local_path = url_mapping[url]
                return f'![{alt_text}]({local_path})'
            
            # Check if it's a full URL that we might have downloaded
            for original_url, local_path in url_mapping.items():
                if url == original_url or url.endswith(original_url.split('/')[-1]):
                    return f'![{alt_text}]({local_path})'
                    
            return match.group(0)  # Return unchanged if not found
        
        return image_pattern.sub(replace_url, markdown_content)
    
    def process_markdown_with_images(self, markdown_content: str, html_content: str, 
                                   base_url: str, output_dir: Path,
                                   progress: Optional[Progress] = None) -> str:
        """Process markdown content, downloading and rewriting image URLs.
        
        Args:
            markdown_content: Converted markdown content
            html_content: Original HTML content
            base_url: Base URL of the page
            output_dir: Directory for output
            progress: Optional progress bar
            
        Returns:
            Markdown content with local image references
        """
        # Extract image URLs from HTML
        image_urls = self.extract_image_urls(html_content, base_url)
        
        if not image_urls:
            return markdown_content
            
        # Download images
        task = None
        if progress:
            task = progress.add_task("Downloading images...", total=len(image_urls))
            
        url_mapping = self.download_images(image_urls, output_dir, progress, task)
        
        # Rewrite URLs in markdown
        return self.rewrite_image_urls(markdown_content, url_mapping)