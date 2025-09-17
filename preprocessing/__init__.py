"""
Site Analysis Preprocessing Module

This module provides tools for preprocessing websites before analysis:
- URL processing and screenshot capture
- HTML content extraction
- Redirect handling
- Data storage preparation
"""

from .scraper import SiteScraper, ScrapingConfig, ScrapingResult, SSLInfo
from .tools import scrape_websites, check_ssl_certificates, load_urls_from_file, AVAILABLE_TOOLS

# Agno tools (optional import - only if agno is available or for future use)
try:
    from .agno_tools import AGNO_TOOLS, TOOL_METADATA, AGNO_AVAILABLE
    __all__ = [
        'SiteScraper', 'ScrapingConfig', 'ScrapingResult', 'SSLInfo',
        'scrape_websites', 'check_ssl_certificates', 'load_urls_from_file', 'AVAILABLE_TOOLS',
        'AGNO_TOOLS', 'TOOL_METADATA', 'AGNO_AVAILABLE'
    ]
except ImportError as e:
    # agno_tools.py import failed (shouldn't happen since we don't require agno)
    __all__ = [
        'SiteScraper', 'ScrapingConfig', 'ScrapingResult', 'SSLInfo',
        'scrape_websites', 'check_ssl_certificates', 'load_urls_from_file', 'AVAILABLE_TOOLS'
    ]