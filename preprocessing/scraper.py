#!/usr/bin/env python3
"""
Site Scraper - Preprocessing Tool

Captures screenshots and HTML content from a list of URLs.
Handles redirects, timeouts, and data extraction for subsequent analysis.
"""

import asyncio
import hashlib
import json
import re
import ssl
import socket
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin

import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = structlog.get_logger()


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


class SiteScraper:
    """Main scraper class for capturing website screenshots and HTML content."""
    
    def __init__(self, config: ScrapingConfig):
        self.config = config
        self.results: List[ScrapingResult] = []
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        
    async def start(self):
        """Initialize browser and context."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
        self.context = await self.browser.new_context(
            viewport={'width': self.config.viewport_width, 'height': self.config.viewport_height},
            user_agent=self.config.user_agent
        )
        logger.info("browser_initialized", 
                   viewport=f"{self.config.viewport_width}x{self.config.viewport_height}")
    
    async def close(self):
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
        logger.info("browser_closed")
    
    def extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return "unknown"
    
    def extract_company_name(self, html_content: str, url: str) -> str:
        """Extract company name from HTML content."""
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
            domain = self.extract_domain(url)
            return domain.replace('www.', '').replace('.com', '').replace('.co.uk', '').title()
            
        except Exception as e:
            logger.warning("company_name_extraction_failed", url=url, error=str(e))
            return self.extract_domain(url)
    
    def calculate_screenshot_hash(self, screenshot_data: bytes) -> str:
        """Calculate SHA-256 hash of screenshot for deduplication."""
        return hashlib.sha256(screenshot_data).hexdigest()
    
    def load_html_content(self, result: ScrapingResult) -> str:
        """Load HTML content from file for a scraping result."""
        if not result.html_path:
            return ""
        
        try:
            html_file_path = self.config.output_dir / result.html_path
            with open(html_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.warning("html_load_failed", 
                         html_path=result.html_path, 
                         error=str(e))
            return ""
    
    async def check_ssl_certificate(self, url: str) -> SSLInfo:
        """Check SSL certificate information for a URL."""
        parsed_url = urlparse(url)
        
        # If not HTTPS, return basic info
        if parsed_url.scheme != 'https':
            return SSLInfo(
                has_ssl=False,
                is_valid=False,
                certificate_error="Not using HTTPS"
            )
        
        hostname = parsed_url.hostname
        port = parsed_url.port or 443
        
        if not hostname:
            return SSLInfo(
                has_ssl=False,
                is_valid=False,
                certificate_error="Invalid hostname"
            )
        
        try:
            # Create SSL context
            context = ssl.create_default_context()
            
            # Connect and get certificate
            loop = asyncio.get_event_loop()
            
            def get_certificate():
                with socket.create_connection((hostname, port), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        return ssock.getpeercert()
            
            # Run in thread pool to avoid blocking
            cert = await loop.run_in_executor(None, get_certificate)
            
            if not cert:
                return SSLInfo(
                    has_ssl=True,
                    is_valid=False,
                    certificate_error="Could not retrieve certificate"
                )
            
            # Parse certificate information
            subject = dict(x[0] for x in cert.get('subject', []))
            issuer = dict(x[0] for x in cert.get('issuer', []))
            
            # Parse expiry date
            expires_str = cert.get('notAfter')
            expires_date = None
            days_until_expiry = None
            
            if expires_str:
                try:
                    # Parse certificate date format: 'Jan  1 00:00:00 2025 GMT'
                    expires_dt = datetime.strptime(expires_str, '%b %d %H:%M:%S %Y %Z')
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                    expires_date = expires_dt.isoformat()
                    
                    # Calculate days until expiry
                    now = datetime.now(timezone.utc)
                    days_until_expiry = (expires_dt - now).days
                    
                except ValueError as e:
                    logger.warning("certificate_date_parse_failed", 
                                 hostname=hostname, 
                                 date_string=expires_str,
                                 error=str(e))
            
            return SSLInfo(
                has_ssl=True,
                is_valid=True,
                issuer=issuer.get('organizationName', issuer.get('commonName', 'Unknown')),
                subject=subject.get('commonName', hostname),
                expires_date=expires_date,
                days_until_expiry=days_until_expiry
            )
            
        except ssl.SSLError as e:
            return SSLInfo(
                has_ssl=True,
                is_valid=False,
                certificate_error=f"SSL Error: {str(e)}"
            )
        except socket.timeout:
            return SSLInfo(
                has_ssl=True,
                is_valid=False,
                certificate_error="Connection timeout"
            )
        except Exception as e:
            return SSLInfo(
                has_ssl=True,
                is_valid=False,
                certificate_error=f"Certificate check failed: {str(e)}"
            )
    
    def detect_bot_protection(self, html_content: str, error_message: Optional[str] = None) -> BotProtectionInfo:
        """Detect bot protection measures based on HTML content and error messages."""
        indicators = []
        
        # Known bot protection indicators (from main site analyser)
        cloudflare_indicators = [
            "cloudflare", "cf-ray", "cf-mitigated", "checking your browser",
            "ddos protection by cloudflare", "attention required", "ray id:",
        ]
        
        ddos_guard_indicators = [
            "ddos-guard", "checking your browser before accessing",
            "ddosguard.net", "under ddos attack",
        ]
        
        recaptcha_indicators = [
            "recaptcha", "i'm not a robot", "google.com/recaptcha",
            "verify you are human",
        ]
        
        rate_limit_indicators = [
            "rate limit", "too many requests", "requests per minute",
            "try again later", "temporary block",
        ]
        
        generic_bot_indicators = [
            "bot protection", "automated traffic", "suspicious activity",
            "access denied", "forbidden", "verification required", "human verification",
        ]
        
        # Analyze HTML content
        if html_content:
            html_lower = html_content.lower()
            
            # Check for Cloudflare indicators
            for indicator in cloudflare_indicators:
                if indicator in html_lower:
                    indicators.append(f"cloudflare_{indicator.replace(' ', '_')}")
            
            # Check for DDoS Guard indicators  
            for indicator in ddos_guard_indicators:
                if indicator in html_lower:
                    indicators.append(f"ddos_guard_{indicator.replace(' ', '_')}")
            
            # Check for reCAPTCHA indicators
            for indicator in recaptcha_indicators:
                if indicator in html_lower:
                    indicators.append(f"recaptcha_{indicator.replace(' ', '_')}")
            
            # Check for rate limit indicators
            for indicator in rate_limit_indicators:
                if indicator in html_lower:
                    indicators.append(f"rate_limit_{indicator.replace(' ', '_')}")
            
            # Check for generic bot protection
            for indicator in generic_bot_indicators:
                if indicator in html_lower:
                    indicators.append(f"generic_{indicator.replace(' ', '_')}")
            
            # Check for JavaScript challenges
            if "challenge" in html_lower and ("javascript" in html_lower or "js" in html_lower):
                indicators.append("javascript_challenge")
            
            # Check for meta refresh redirects (common in challenges)
            if re.search(r'<meta[^>]*http-equiv=["\']?refresh["\']?', html_lower):
                indicators.append("meta_refresh_redirect")
        
        # Analyze error messages
        if error_message:
            error_lower = error_message.lower()
            
            # HTTP status code indicators
            if "403" in error_message or "forbidden" in error_lower:
                indicators.append("http_403_forbidden")
            if "429" in error_message or "too many requests" in error_lower:
                indicators.append("http_429_rate_limit")
            if "503" in error_message or "service unavailable" in error_lower:
                indicators.append("http_503_service_unavailable")
            
            # Common bot protection error phrases
            bot_protection_phrases = [
                "access denied", "forbidden", "blocked", "suspicious activity",
                "automated traffic", "bot detected", "rate limit", "too many requests",
                "verification required", "challenge",
            ]
            
            for phrase in bot_protection_phrases:
                if phrase in error_lower:
                    indicators.append(f"error_message_{phrase.replace(' ', '_')}")
        
        # Determine protection type and confidence
        if not indicators:
            return BotProtectionInfo(detected=False)
        
        protection_type, confidence = self._determine_protection_type(indicators)
        detected = confidence > 0.3  # Threshold for detection
        
        return BotProtectionInfo(
            detected=detected,
            protection_type=protection_type,
            indicators=list(set(indicators)),  # Remove duplicates
            confidence=confidence
        )
    
    def _determine_protection_type(self, indicators: List[str]) -> Tuple[Optional[str], float]:
        """Determine the type of bot protection and confidence level."""
        cloudflare_score = sum(1 for ind in indicators if "cloudflare" in ind)
        ddos_guard_score = sum(1 for ind in indicators if "ddos_guard" in ind)
        recaptcha_score = sum(1 for ind in indicators if "recaptcha" in ind)
        rate_limit_score = sum(1 for ind in indicators if "rate_limit" in ind or "429" in ind)
        generic_score = sum(1 for ind in indicators if "generic" in ind or "403" in ind or "blocked" in ind)
        
        # Calculate confidence based on number and strength of indicators
        max_score = max(cloudflare_score, ddos_guard_score, recaptcha_score, rate_limit_score, generic_score)
        total_indicators = len(indicators)
        
        # Base confidence on number of indicators and strongest category
        confidence = min((max_score * 0.4) + (total_indicators * 0.1), 1.0)
        
        # Determine protection type
        if cloudflare_score > 0:
            return "cloudflare", max(confidence, 0.7)  # Cloudflare is usually obvious
        elif ddos_guard_score > 0:
            return "ddos_guard", max(confidence, 0.7)
        elif recaptcha_score > 0:
            return "recaptcha", max(confidence, 0.6)
        elif rate_limit_score > 0:
            return "rate_limit", max(confidence, 0.8)  # Rate limits are clear
        elif generic_score > 0:
            return "unknown", max(confidence, 0.4)
        
        return None, confidence
    
    async def scrape_url(self, url: str) -> ScrapingResult:
        """Scrape a single URL and return the result."""
        start_time = asyncio.get_event_loop().time()
        original_url = url
        
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        
        logger.info("scraping_url", url=url, job_id=self.config.job_id)
        
        try:
            page = await self.context.new_page()
            
            # Navigate with timeout
            response = await page.goto(url, timeout=self.config.timeout_ms, wait_until='networkidle')
            
            if response is None:
                raise Exception("Navigation failed - no response")
            
            # Get final URL after redirects
            final_url = page.url
            domain = self.extract_domain(final_url)
            redirected = original_url != final_url
            
            # Get HTML content
            html_content = await page.content()
            
            # Extract company name
            company_name = self.extract_company_name(html_content, final_url)
            
            # Save HTML content to separate file
            html_filename = f"{self.config.job_id}_{domain}_{int(start_time)}.html"
            html_path = self.config.output_dir / "html" / html_filename
            html_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Take screenshot
            screenshot_filename = f"{self.config.job_id}_{domain}_{int(start_time)}.png"
            screenshot_path = self.config.output_dir / "screenshots" / screenshot_filename
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            
            screenshot_data = await page.screenshot(path=str(screenshot_path), full_page=True)
            screenshot_hash = self.calculate_screenshot_hash(screenshot_data)
            
            await page.close()
            
            # Check SSL certificate (after page is closed to avoid conflicts)
            ssl_info = await self.check_ssl_certificate(final_url)
            
            # Detect bot protection
            bot_protection = self.detect_bot_protection(html_content)
            
            # Calculate load time
            end_time = asyncio.get_event_loop().time()
            load_time_ms = int((end_time - start_time) * 1000)
            
            result = ScrapingResult(
                job_id=self.config.job_id,
                original_url=original_url,
                final_url=final_url,
                domain=domain,
                company_name=company_name,
                html_path=str(html_path.relative_to(self.config.output_dir)),
                html_size=len(html_content.encode('utf-8')),
                screenshot_path=str(screenshot_path.relative_to(self.config.output_dir)),
                screenshot_hash=screenshot_hash,
                load_time_ms=load_time_ms,
                viewport_size=f"{self.config.viewport_width}x{self.config.viewport_height}",
                redirected=redirected,
                ssl_info=ssl_info,
                bot_protection=bot_protection,
                status="success"
            )
            
            logger.info("scraping_completed", 
                       url=final_url, 
                       load_time=load_time_ms,
                       redirected=redirected,
                       company=company_name,
                       has_ssl=ssl_info.has_ssl,
                       ssl_valid=ssl_info.is_valid,
                       ssl_expires_days=ssl_info.days_until_expiry,
                       bot_protection_detected=bot_protection.detected,
                       bot_protection_type=bot_protection.protection_type)
            
            return result
            
        except asyncio.TimeoutError:
            logger.warning("scraping_timeout", url=url, timeout_ms=self.config.timeout_ms)
            
            # Still try to check SSL even if page load timed out
            ssl_info = await self.check_ssl_certificate(url)
            
            # Detect bot protection based on timeout (might indicate bot blocking)
            bot_protection = self.detect_bot_protection("", "Page load timeout")
            
            return ScrapingResult(
                job_id=self.config.job_id,
                original_url=original_url,
                final_url=url,
                domain=self.extract_domain(url),
                company_name=self.extract_domain(url),
                html_path=None,
                html_size=0,
                screenshot_path=None,
                screenshot_hash=None,
                load_time_ms=self.config.timeout_ms,
                viewport_size=f"{self.config.viewport_width}x{self.config.viewport_height}",
                redirected=False,
                ssl_info=ssl_info,
                bot_protection=bot_protection,
                status="timeout",
                error_message="Page load timeout"
            )
            
        except Exception as e:
            logger.error("scraping_failed", url=url, error=str(e))
            
            # Still try to check SSL even if scraping failed
            try:
                ssl_info = await self.check_ssl_certificate(url)
            except Exception:
                # If SSL check also fails, create a basic SSL info
                ssl_info = SSLInfo(
                    has_ssl=url.startswith('https://'),
                    is_valid=False,
                    certificate_error="Could not check certificate due to scraping failure"
                )
            
            # Detect bot protection based on error message
            bot_protection = self.detect_bot_protection("", str(e))
            
            return ScrapingResult(
                job_id=self.config.job_id,
                original_url=original_url,
                final_url=url,
                domain=self.extract_domain(url),
                company_name=self.extract_domain(url),
                html_path=None,
                html_size=0,
                screenshot_path=None,
                screenshot_hash=None,
                load_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                viewport_size=f"{self.config.viewport_width}x{self.config.viewport_height}",
                redirected=False,
                ssl_info=ssl_info,
                bot_protection=bot_protection,
                status="error",
                error_message=str(e)
            )
    
    async def scrape_urls(self, urls: List[str]) -> List[ScrapingResult]:
        """Scrape multiple URLs with concurrency control."""
        logger.info("starting_batch_scrape", 
                   url_count=len(urls), 
                   job_id=self.config.job_id,
                   max_concurrent=self.config.max_concurrent)
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        async def scrape_with_semaphore(url: str) -> ScrapingResult:
            async with semaphore:
                return await self.scrape_url(url)
        
        # Execute all scraping tasks
        tasks = [scrape_with_semaphore(url) for url in urls]
        self.results = await asyncio.gather(*tasks, return_exceptions=False)
        
        # Count results by status
        success_count = sum(1 for r in self.results if r.status == "success")
        timeout_count = sum(1 for r in self.results if r.status == "timeout") 
        error_count = sum(1 for r in self.results if r.status == "error")
        
        logger.info("batch_scrape_completed",
                   total=len(urls),
                   success=success_count,
                   timeout=timeout_count,
                   error=error_count,
                   job_id=self.config.job_id)
        
        return self.results
    
    def save_results_json(self, output_path: Optional[Path] = None) -> Path:
        """Save results to JSON file."""
        if output_path is None:
            output_path = self.config.output_dir / f"{self.config.job_id}_scraping_results.json"
        
        # Convert results to serializable format
        results_data = {
            "job_id": self.config.job_id,
            "timestamp": datetime.now().isoformat(),
            "config": {
                "viewport_size": f"{self.config.viewport_width}x{self.config.viewport_height}",
                "timeout_ms": self.config.timeout_ms,
                "max_concurrent": self.config.max_concurrent
            },
            "summary": {
                "total_urls": len(self.results),
                "successful": sum(1 for r in self.results if r.status == "success"),
                "timeouts": sum(1 for r in self.results if r.status == "timeout"),
                "errors": sum(1 for r in self.results if r.status == "error")
            },
            "results": [asdict(result) for result in self.results]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, indent=2, ensure_ascii=False)
        
        logger.info("results_saved", file=str(output_path), count=len(self.results))
        return output_path
    
    @classmethod
    def load_urls_from_file(cls, file_path: Path) -> List[str]:
        """Load URLs from a text file (one per line)."""
        urls = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#'):  # Skip empty lines and comments
                    urls.append(line)
        
        logger.info("urls_loaded_from_file", file=str(file_path), count=len(urls))
        return urls