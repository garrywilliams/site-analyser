"""Web scraping and screenshot capture processor."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from .base import BaseProcessor

logger = structlog.get_logger()


class WebScraperProcessor(BaseProcessor):
    """Processor for web scraping HTML content and capturing screenshots."""
    
    def __init__(self, config):
        super().__init__(config)
        self.version = "1.0.0"
        self.browser: Optional[Browser] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.playwright = await async_playwright().start()
        
        # Check if we should use system Chrome (for corporate environments)
        import os
        use_system_chrome = os.getenv('USE_SYSTEM_CHROME', '').lower() in ('true', '1', 'yes')
        
        browser_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
            "--ignore-certificate-errors-spki-list",
            "--ignore-certificate-errors",
            "--ignore-ssl-errors",
            "--accept-insecure-certs"
        ]
        
        if use_system_chrome:
            # Try to use system Chrome installation
            logger.info("using_system_chrome", message="Attempting to use system Chrome browser")
            try:
                # Common Chrome paths
                chrome_paths = [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
                    "/usr/bin/google-chrome",  # Linux Google Chrome
                    "/usr/bin/google-chrome-stable",  # Linux Google Chrome (stable)
                    "/usr/bin/chromium-browser",  # Linux Chromium
                    "/usr/bin/chromium",  # Linux Chromium (alternative)
                    "/snap/bin/chromium",  # Snap Chromium
                    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",  # Windows
                    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",  # Windows x86
                ]
                
                chrome_path = None
                for path in chrome_paths:
                    if os.path.exists(path):
                        chrome_path = path
                        break
                
                if chrome_path:
                    self.browser = await self.playwright.chromium.launch(
                        executable_path=chrome_path,
                        headless=True,
                        args=browser_args
                    )
                    logger.info("system_chrome_used", path=chrome_path)
                    return self
                else:
                    logger.warning("system_chrome_not_found", message="System Chrome not found, falling back to Playwright Chrome")
            except Exception as e:
                logger.warning("system_chrome_failed", error=str(e), message="Failed to use system Chrome, falling back")
        
        # Default: Use Playwright's Chrome
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=browser_args
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Scrape HTML content and capture screenshot."""
        start_time = datetime.now()
        page: Optional[Page] = None
        
        try:
            if not self.browser:
                raise RuntimeError("Browser not initialized. Use async context manager.")
            
            page = await self.browser.new_page()
            
            # Set viewport for consistent screenshots
            viewport_width = getattr(self.config.processing_config, 'viewport_width', 1920)
            viewport_height = getattr(self.config.processing_config, 'viewport_height', 1080)
            await page.set_viewport_size({"width": viewport_width, "height": viewport_height})
            
            # Navigate to page with timeout
            load_start = datetime.now()
            
            try:
                response = await page.goto(
                    url,
                    timeout=self.config.processing_config.screenshot_timeout_seconds * 1000,
                    wait_until="domcontentloaded"
                )
                
                load_time = (datetime.now() - load_start).total_seconds() * 1000
                result.load_time_ms = int(load_time)
                result.site_loads = response is not None and response.status < 400
                
                if not result.site_loads:
                    result.error_message = f"HTTP {response.status if response else 'No response'}"
                    
            except Exception as e:
                result.site_loads = False
                result.error_message = f"Page load failed: {str(e)}"
                logger.warning("page_load_failed", url=url, error=str(e))
            
            if result.site_loads:
                # Extract HTML content
                try:
                    result.html_content = await page.content()
                    logger.debug("html_content_extracted", url=url, 
                               content_length=len(result.html_content))
                except Exception as e:
                    logger.warning("html_extraction_failed", url=url, error=str(e))
                
                # Capture screenshot
                try:
                    await self._capture_screenshot(page, url, result)
                except Exception as e:
                    logger.warning("screenshot_capture_failed", url=url, error=str(e))
            
            logger.info(
                "web_scraping_complete",
                url=url,
                site_loads=result.site_loads,
                has_html=bool(result.html_content),
                has_screenshot=bool(result.screenshot_path),
                load_time_ms=result.load_time_ms
            )
            
        except Exception as e:
            logger.error("web_scraping_failed", url=url, error=str(e))
            result.site_loads = False
            result.error_message = f"Web scraping failed: {str(e)}"
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
                
        finally:
            if page:
                await page.close()
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result
    
    async def _capture_screenshot(self, page: Page, url: str, result: SiteAnalysisResult) -> None:
        """Capture a screenshot of the current page."""
        logger.info("screenshot_capture_started", url=url)
        
        # Ensure screenshots directory exists
        screenshots_dir = self.config.output_config.screenshots_directory
        logger.info("screenshot_directory_check", directory=str(screenshots_dir.absolute()), exists=screenshots_dir.exists())
        
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        logger.info("screenshot_directory_created", directory=str(screenshots_dir.absolute()))
        
        # Generate filename from URL
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        safe_filename = f"{parsed_url.netloc.replace('.', '_')}_{parsed_url.path.replace('/', '_').strip('_')}"
        if not safe_filename or safe_filename == "_":
            safe_filename = "root"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_filename = f"{safe_filename}_{timestamp}.png"
        screenshot_path = screenshots_dir / screenshot_filename
        
        logger.info("screenshot_path_generated", 
                   url=url, 
                   filename=screenshot_filename, 
                   full_path=str(screenshot_path.absolute()))
        
        # Wait a moment for any dynamic content to load
        await asyncio.sleep(2)
        
        try:
            # Take full page screenshot
            logger.info("taking_screenshot", url=url, path=str(screenshot_path))
            await page.screenshot(
                path=str(screenshot_path),
                full_page=True,
                type="png"
            )
            
            # Verify screenshot was created
            if screenshot_path.exists():
                file_size = screenshot_path.stat().st_size
                logger.info("screenshot_created_successfully", 
                           url=url, 
                           path=str(screenshot_path.absolute()),
                           size_bytes=file_size)
            else:
                logger.error("screenshot_file_not_found", url=url, path=str(screenshot_path.absolute()))
            
            result.screenshot_path = screenshot_path
            
        except Exception as e:
            logger.error("screenshot_capture_failed", url=url, error=str(e), path=str(screenshot_path))
            raise
        
        logger.info("screenshot_capture_completed", url=url, path=str(screenshot_path))