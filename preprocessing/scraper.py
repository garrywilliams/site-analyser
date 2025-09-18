#!/usr/bin/env python3
"""
Site Scraper - Preprocessing Tool (Refactored)

Captures screenshots and HTML content from a list of URLs.
Handles redirects, timeouts, and data extraction for subsequent analysis.

This is the refactored version using modular components.
"""

import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import structlog
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .models import ScrapingConfig, ScrapingResult, SSLInfo, BotProtectionInfo
from .ssl_checker import SSLChecker
from .bot_detector import BotDetector
from .content_extractor import ContentExtractor

logger = structlog.get_logger()

__all__ = ['SiteScraper']


class SiteScraper:
    """Main scraper class for capturing website screenshots and content."""
    
    def __init__(self, config: ScrapingConfig):
        self.config = config
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.results: List[ScrapingResult] = []
        
    async def __aenter__(self):
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self):
        """Start the browser and create context."""
        if self.browser is not None:
            return
            
        logger.info("starting_browser", job_id=self.config.job_id)
        
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            viewport={"width": self.config.viewport_width, "height": self.config.viewport_height},
            user_agent=self.config.user_agent
        )
    
    async def close(self):
        """Close browser and cleanup."""
        if self.context:
            await self.context.close()
            self.context = None
        
        if self.browser:
            await self.browser.close()
            self.browser = None
    
    def load_html_content(self, result: ScrapingResult) -> str:
        """Load HTML content from the saved file."""
        if not result.html_path:
            return ""
        
        try:
            html_file_path = self.config.output_dir / result.html_path
            with open(html_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error("html_load_failed", 
                        path=result.html_path,
                        error=str(e))
            return ""
    
    async def check_ssl_certificate(self, url: str) -> SSLInfo:
        """Check SSL certificate information for a URL."""
        return await SSLChecker.check_certificate(url)
    
    async def scrape_url(self, url: str) -> ScrapingResult:
        """Scrape a single URL and return the result."""
        start_time = asyncio.get_event_loop().time()
        original_url = url
        
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        logger.info("scraping_url", url=url, job_id=self.config.job_id)
        
        # Extract initial domain
        domain = ContentExtractor.extract_domain(url)
        
        # Check SSL certificate first (lightweight operation)
        ssl_info = await self.check_ssl_certificate(url)
        
        # Initialize default result for error cases
        def create_error_result(status: str, error_msg: str, 
                              final_url: str = None, 
                              redirected: bool = False,
                              load_time_ms: int = None) -> ScrapingResult:
            
            # Detect bot protection from error message
            bot_protection = BotDetector.detect_protection("", error_msg)
            
            return ScrapingResult(
                job_id=self.config.job_id,
                original_url=original_url,
                final_url=final_url or url,
                domain=domain,
                company_name=None,
                html_path=None,
                html_size=0,
                screenshot_path=None,
                screenshot_hash=None,
                load_time_ms=load_time_ms or int((asyncio.get_event_loop().time() - start_time) * 1000),
                viewport_size=f"{self.config.viewport_width}x{self.config.viewport_height}",
                redirected=redirected,
                ssl_info=ssl_info,
                bot_protection=bot_protection,
                status=status,
                error_message=error_msg
            )
        
        try:
            # Create new page
            page: Page = await self.context.new_page()
            
            try:
                # Navigate to URL with timeout
                response = await page.goto(url, timeout=self.config.timeout_ms, wait_until='networkidle')
                
                # Calculate load time
                load_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
                
                # Get final URL and check for redirects
                final_url = page.url
                redirected = final_url != url
                domain = ContentExtractor.extract_domain(final_url)
                
                # Get HTML content
                html_content = await page.content()
                
                # Detect bot protection
                bot_protection = BotDetector.detect_protection(html_content)
                
                # Extract company name
                company_name = ContentExtractor.extract_company_name(html_content, final_url)
                
                # Save HTML to file
                timestamp = int(datetime.now().timestamp())
                safe_domain = domain.replace('/', '_').replace(':', '_')
                html_filename = f"{self.config.job_id}_{safe_domain}_{timestamp}.html"
                html_path = f"html/{html_filename}"
                full_html_path = self.config.output_dir / html_path
                full_html_path.parent.mkdir(exist_ok=True)
                
                with open(full_html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                html_size = len(html_content.encode('utf-8'))
                
                # Take screenshot
                screenshot_filename = f"{self.config.job_id}_{safe_domain}_{timestamp}.png"
                screenshot_path = f"screenshots/{screenshot_filename}"
                full_screenshot_path = self.config.output_dir / screenshot_path
                full_screenshot_path.parent.mkdir(exist_ok=True)
                
                screenshot_data = await page.screenshot(path=full_screenshot_path, full_page=True)
                screenshot_hash = ContentExtractor.calculate_screenshot_hash(screenshot_data)
                
                logger.info("scraping_completed", 
                           url=final_url, 
                           load_time_ms=load_time_ms,
                           html_size=html_size,
                           company=company_name)
                
                return ScrapingResult(
                    job_id=self.config.job_id,
                    original_url=original_url,
                    final_url=final_url,
                    domain=domain,
                    company_name=company_name,
                    html_path=html_path,
                    html_size=html_size,
                    screenshot_path=screenshot_path,
                    screenshot_hash=screenshot_hash,
                    load_time_ms=load_time_ms,
                    viewport_size=f"{self.config.viewport_width}x{self.config.viewport_height}",
                    redirected=redirected,
                    ssl_info=ssl_info,
                    bot_protection=bot_protection,
                    status="success"
                )
                
            except asyncio.TimeoutError:
                logger.warning("scraping_timeout", url=url, timeout_ms=self.config.timeout_ms)
                return create_error_result("timeout", f"Page load timeout after {self.config.timeout_ms}ms")
                
            except Exception as e:
                error_msg = str(e)
                logger.error("scraping_error", url=url, error=error_msg)
                
                # Try to get final URL if navigation partially succeeded
                final_url = url
                redirected = False
                try:
                    final_url = page.url
                    redirected = final_url != url
                except:
                    pass
                
                return create_error_result("error", error_msg, final_url, redirected)
                
            finally:
                await page.close()
                
        except Exception as e:
            error_msg = f"Browser error: {str(e)}"
            logger.error("browser_error", url=url, error=error_msg)
            return create_error_result("error", error_msg)
    
    async def scrape_urls(self, urls: List[str]) -> List[ScrapingResult]:
        """Scrape multiple URLs concurrently."""
        if not self.browser:
            await self.start()
        
        logger.info("starting_batch_scraping", 
                   url_count=len(urls), 
                   max_concurrent=self.config.max_concurrent,
                   job_id=self.config.job_id)
        
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        
        async def scrape_with_semaphore(url: str) -> ScrapingResult:
            async with semaphore:
                result = await self.scrape_url(url)
                self.results.append(result)
                return result
        
        # Create tasks for all URLs
        tasks = [scrape_with_semaphore(url) for url in urls]
        
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("task_exception", url=urls[i], error=str(result))
                # Create error result for failed tasks
                error_result = ScrapingResult(
                    job_id=self.config.job_id,
                    original_url=urls[i],
                    final_url=urls[i],
                    domain=ContentExtractor.extract_domain(urls[i]),
                    company_name=None,
                    html_path=None,
                    html_size=0,
                    screenshot_path=None,
                    screenshot_hash=None,
                    load_time_ms=0,
                    viewport_size=f"{self.config.viewport_width}x{self.config.viewport_height}",
                    redirected=False,
                    ssl_info=SSLInfo(has_ssl=False, is_valid=False, certificate_error="Task failed"),
                    bot_protection=BotProtectionInfo(detected=False),
                    status="error",
                    error_message=str(result)
                )
                final_results.append(error_result)
            else:
                final_results.append(result)
        
        return final_results
    
    def save_results_json(self, output_path: Optional[Path] = None) -> Path:
        """Save scraping results to JSON file."""
        if output_path is None:
            output_path = self.config.output_dir / f"{self.config.job_id}_scraping_results.json"
        
        # Calculate summary statistics
        successful = sum(1 for r in self.results if r.status == "success")
        timeouts = sum(1 for r in self.results if r.status == "timeout")
        errors = sum(1 for r in self.results if r.status == "error")
        
        # Create output data
        output_data = {
            "job_id": self.config.job_id,
            "timestamp": datetime.now().isoformat(),
            "config": {
                "viewport_size": f"{self.config.viewport_width}x{self.config.viewport_height}",
                "timeout_ms": self.config.timeout_ms,
                "max_concurrent": self.config.max_concurrent
            },
            "summary": {
                "total_urls": len(self.results),
                "successful": successful,
                "timeouts": timeouts,
                "errors": errors
            },
            "results": [asdict(result) for result in self.results]
        }
        
        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        logger.info("results_saved", 
                   path=output_path, 
                   total_results=len(self.results),
                   successful=successful)
        
        return output_path
    
    @classmethod
    def load_urls_from_file(cls, file_path: Path) -> List[str]:
        """Load URLs from a text file, filtering out comments and empty lines."""
        urls = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        urls.append(line)
            
            logger.info("urls_loaded_from_file", 
                       file_path=file_path, 
                       url_count=len(urls))
            
        except Exception as e:
            logger.error("url_file_load_failed", 
                        file_path=file_path, 
                        error=str(e))
            
        return urls