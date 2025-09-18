#!/usr/bin/env python3
"""
HTML Content Extractor

Extracts useful information from HTML content including company names, 
metadata, and other structured data.
"""

import hashlib
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()

__all__ = ['ContentExtractor']


class ContentExtractor:
    """HTML content extraction and analysis utilities."""
    
    @staticmethod
    def extract_domain(url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return url
    
    @staticmethod
    def extract_company_name(html_content: str, url: str) -> str:
        """
        Extract company name from HTML content using multiple strategies.
        
        Args:
            html_content: The HTML content to analyze
            url: The URL for fallback domain extraction
            
        Returns:
            Extracted company name or domain-based fallback
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try multiple methods to get company name
            candidates = []
            
            # 1. OpenGraph site name
            og_site = soup.find('meta', property='og:site_name')
            if og_site and og_site.get('content'):
                candidates.append(og_site.get('content').strip())
            
            # 2. Title tag (clean up common patterns)
            title = soup.find('title')
            if title:
                title_text = title.get_text().strip()
                # Remove common suffixes
                for suffix in [' - Home', ' | Home', ' - Official Site', ' | Official Site']:
                    if title_text.endswith(suffix):
                        title_text = title_text[:-len(suffix)].strip()
                if title_text and len(title_text) < 100:
                    candidates.append(title_text)
            
            # 3. First h1 tag
            h1 = soup.find('h1')
            if h1:
                h1_text = h1.get_text().strip()
                if h1_text and len(h1_text) < 100:
                    candidates.append(h1_text)
            
            # Return first reasonable candidate
            for candidate in candidates:
                if candidate and len(candidate.strip()) > 2:
                    return candidate.strip()
            
            # Fallback to domain-based name
            domain = ContentExtractor.extract_domain(url)
            return domain.replace('www.', '').replace('.com', '').replace('.co.uk', '').title()
            
        except Exception as e:
            logger.warning("company_name_extraction_failed", url=url, error=str(e))
            return ContentExtractor.extract_domain(url)
    
    @staticmethod
    def extract_metadata(html_content: str) -> Dict[str, Any]:
        """
        Extract various metadata from HTML content.
        
        Args:
            html_content: The HTML content to analyze
            
        Returns:
            Dictionary containing extracted metadata
        """
        metadata = {
            'title': None,
            'description': None,
            'keywords': None,
            'og_title': None,
            'og_description': None,
            'og_image': None,
            'canonical_url': None,
            'language': None,
            'charset': None
        }
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Title
            title_tag = soup.find('title')
            if title_tag:
                metadata['title'] = title_tag.get_text().strip()
            
            # Meta description
            desc_tag = soup.find('meta', attrs={'name': 'description'})
            if desc_tag:
                metadata['description'] = desc_tag.get('content', '').strip()
            
            # Meta keywords
            keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
            if keywords_tag:
                metadata['keywords'] = keywords_tag.get('content', '').strip()
            
            # OpenGraph metadata
            og_title = soup.find('meta', property='og:title')
            if og_title:
                metadata['og_title'] = og_title.get('content', '').strip()
                
            og_desc = soup.find('meta', property='og:description')
            if og_desc:
                metadata['og_description'] = og_desc.get('content', '').strip()
                
            og_image = soup.find('meta', property='og:image')
            if og_image:
                metadata['og_image'] = og_image.get('content', '').strip()
            
            # Canonical URL
            canonical = soup.find('link', rel='canonical')
            if canonical:
                metadata['canonical_url'] = canonical.get('href', '').strip()
            
            # Language
            html_tag = soup.find('html')
            if html_tag:
                metadata['language'] = html_tag.get('lang', '').strip()
            
            # Charset
            charset_tag = soup.find('meta', charset=True)
            if charset_tag:
                metadata['charset'] = charset_tag.get('charset', '').strip()
            else:
                # Try http-equiv content-type
                content_type = soup.find('meta', attrs={'http-equiv': 'Content-Type'})
                if content_type:
                    content = content_type.get('content', '')
                    charset_match = re.search(r'charset=([^;]+)', content)
                    if charset_match:
                        metadata['charset'] = charset_match.group(1).strip()
            
        except Exception as e:
            logger.warning("metadata_extraction_failed", error=str(e))
        
        return metadata
    
    @staticmethod
    def extract_links(html_content: str, base_url: str) -> List[Dict[str, str]]:
        """
        Extract all links from HTML content.
        
        Args:
            html_content: The HTML content to analyze
            base_url: Base URL for resolving relative links
            
        Returns:
            List of dictionaries containing link information
        """
        links = []
        
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin, urlparse
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            for link_tag in soup.find_all('a', href=True):
                href = link_tag.get('href', '').strip()
                if not href:
                    continue
                
                # Resolve relative URLs
                full_url = urljoin(base_url, href)
                
                # Get link text
                link_text = link_tag.get_text().strip()
                
                # Get title attribute if present
                title = link_tag.get('title', '').strip()
                
                links.append({
                    'url': full_url,
                    'text': link_text,
                    'title': title,
                    'original_href': href,
                    'is_external': urlparse(full_url).netloc != urlparse(base_url).netloc
                })
                
        except Exception as e:
            logger.warning("link_extraction_failed", base_url=base_url, error=str(e))
        
        return links
    
    @staticmethod
    def calculate_screenshot_hash(screenshot_data: bytes) -> str:
        """
        Calculate SHA-256 hash of screenshot for deduplication.
        
        Args:
            screenshot_data: Binary screenshot data
            
        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(screenshot_data).hexdigest()
    
    @staticmethod
    def get_content_summary(html_content: str) -> Dict[str, Any]:
        """
        Get a summary of HTML content characteristics.
        
        Args:
            html_content: The HTML content to analyze
            
        Returns:
            Dictionary containing content summary information
        """
        summary = {
            'size_bytes': len(html_content),
            'size_kb': round(len(html_content) / 1024, 2),
            'line_count': len(html_content.splitlines()),
            'has_javascript': False,
            'has_css': False,
            'has_images': False,
            'has_forms': False,
            'external_resources': 0
        }
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Check for various content types
            summary['has_javascript'] = bool(soup.find('script'))
            summary['has_css'] = bool(soup.find('style') or soup.find('link', rel='stylesheet'))
            summary['has_images'] = bool(soup.find('img'))
            summary['has_forms'] = bool(soup.find('form'))
            
            # Count external resources
            external_count = 0
            for tag in soup.find_all(['script', 'link', 'img']):
                src_attr = tag.get('src') or tag.get('href')
                if src_attr and (src_attr.startswith('http') or src_attr.startswith('//')):
                    external_count += 1
            
            summary['external_resources'] = external_count
            
        except Exception as e:
            logger.warning("content_summary_failed", error=str(e))
        
        return summary