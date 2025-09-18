#!/usr/bin/env python3
"""
Data models for the site scraper preprocessing module.

Contains all dataclass definitions used throughout the scraping process.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

__all__ = ['ScrapingConfig', 'SSLInfo', 'BotProtectionInfo', 'ScrapingResult']


@dataclass
class ScrapingConfig:
    """Configuration for the scraping process."""
    job_id: str
    output_dir: Path
    viewport_width: int = 1920
    viewport_height: int = 1080
    timeout_ms: int = 30000
    max_concurrent: int = 5
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    def __post_init__(self):
        """Ensure output directory exists."""
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class SSLInfo:
    """SSL certificate information."""
    has_ssl: bool
    is_valid: bool
    issuer: Optional[str] = None
    subject: Optional[str] = None
    expires_date: Optional[str] = None  # ISO format
    days_until_expiry: Optional[int] = None
    certificate_error: Optional[str] = None


@dataclass
class BotProtectionInfo:
    """Bot protection detection information."""
    detected: bool
    protection_type: Optional[str] = None  # "cloudflare", "ddos_guard", "recaptcha", "rate_limit", "unknown"
    indicators: List[str] = None  # List of evidence that suggests bot protection
    confidence: float = 0.0  # 0.0 to 1.0 confidence that this is bot protection
    
    def __post_init__(self):
        """Set default empty list for indicators."""
        if self.indicators is None:
            self.indicators = []


@dataclass  
class ScrapingResult:
    """Result of scraping a single URL."""
    job_id: str
    original_url: str
    final_url: str
    domain: str
    company_name: Optional[str]
    html_path: Optional[str]  # Path to saved HTML file
    html_size: int  # Size in bytes for reference
    screenshot_path: Optional[str]
    screenshot_hash: Optional[str]
    load_time_ms: int
    viewport_size: str
    redirected: bool
    ssl_info: SSLInfo
    bot_protection: BotProtectionInfo
    status: str  # success, timeout, error
    error_message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()