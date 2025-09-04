"""Web scraping agent using Agno framework."""

import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.tools.reasoning import ReasoningTools
from playwright.async_api import async_playwright
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from ..models.config import SiteAnalyserConfig

logger = structlog.get_logger()

# Pool of realistic user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

# Common viewport sizes
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1600, "height": 900}
]


class WebScraperTool:
    """Custom tool for web scraping with Playwright."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
    
    async def scrape_website(self, url: str) -> dict:
        """Scrape a website and return content and metadata."""
        start_time = datetime.now()
        
        try:
            async with async_playwright() as p:
                # Determine browser args based on stealth mode setting
                base_args = ["--no-sandbox", "--disable-dev-shm-usage"]
                
                if self.config.processing_config.use_stealth_mode:
                    stealth_args = [
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=VizDisplayCompositor",
                        "--disable-web-security",
                        "--disable-features=TranslateUI",
                        "--disable-ipc-flooding-protection",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-default-apps",
                        "--disable-popup-blocking",
                        "--disable-prompt-on-repost",
                        "--disable-hang-monitor",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                        "--disable-background-networking",
                        "--disable-background-timer-throttling",
                        "--force-color-profile=srgb",
                        "--metrics-recording-only",
                        "--disable-background-mode"
                    ]
                    browser_args = base_args + stealth_args
                else:
                    browser_args = base_args
                
                # Launch browser
                browser = await p.chromium.launch(headless=True, args=browser_args)
                
                # Select random user agent and viewport if configured
                if self.config.processing_config.random_user_agents:
                    user_agent = random.choice(USER_AGENTS)
                    viewport = random.choice(VIEWPORTS)
                else:
                    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    viewport = {"width": 1366, "height": 768}
                
                # Create context with browser fingerprint
                context_options = {
                    "viewport": viewport,
                    "user_agent": user_agent,
                    "locale": "en-US",
                    "timezone_id": random.choice(["America/New_York", "America/Los_Angeles", "Europe/London"]) if self.config.processing_config.random_user_agents else "America/New_York"
                }
                
                if self.config.processing_config.use_stealth_mode:
                    context_options["extra_http_headers"] = {
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Cache-Control": "max-age=0"
                    }
                
                context = await browser.new_context(**context_options)
                
                page = await context.new_page()
                
                # Remove webdriver traces if stealth mode is enabled
                if self.config.processing_config.use_stealth_mode:
                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined,
                        });
                        
                        // Remove chrome detection
                        window.chrome = {
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        };
                        
                        // Override plugins
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });
                        
                        // Override languages
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['en-US', 'en']
                        });
                        
                        // Override permissions
                        const originalQuery = window.navigator.permissions.query;
                        window.navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' ?
                                Promise.resolve({ state: Notification.permission }) :
                                originalQuery(parameters)
                        );
                    """)
                
                # Add random mouse movements and delays if human behavior simulation is enabled
                if self.config.processing_config.simulate_human_behavior:
                    await page.mouse.move(random.randint(50, 200), random.randint(100, 300))
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                
                # Navigate to URL with realistic timing
                response = await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Simulate human-like behavior if enabled
                if self.config.processing_config.simulate_human_behavior:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    await page.mouse.move(random.randint(200, 500), random.randint(300, 600))
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                
                # Check for and handle common bot detection if enabled
                page_content = await page.content()
                
                if self.config.processing_config.handle_captcha_challenges:
                    page_text = await page.inner_text('body') if await page.locator('body').count() > 0 else ""
                    
                    # Wait for potential bot checks to complete
                    bot_check_indicators = [
                        "checking your browser",
                        "enable javascript",
                        "cloudflare",
                        "ddos protection",
                        "please wait",
                        "verifying you are human",
                        "captcha",
                        "just a moment"
                    ]
                    
                    if any(indicator in page_text.lower() for indicator in bot_check_indicators):
                        logger.info("bot_detection_wait", url=url, reason="potential_bot_check")
                        
                        # Wait longer and try scrolling
                        wait_time = random.uniform(2, 5)
                        await asyncio.sleep(wait_time)
                        
                        if self.config.processing_config.simulate_human_behavior:
                            await page.mouse.wheel(0, random.randint(300, 700))
                            await asyncio.sleep(random.uniform(1, 3))
                        
                        # Try clicking if there's a button
                        try:
                            # Look for common "I'm not a robot" or verification buttons
                            verify_selectors = [
                                'input[type="checkbox"][id*="recaptcha"]',
                                'button:has-text("Verify")',
                                'button:has-text("Continue")',
                                'input[value="Verify"]',
                                '.cf-browser-verification',
                                '#challenge-form button'
                            ]
                            
                            for selector in verify_selectors:
                                if await page.locator(selector).count() > 0:
                                    await page.click(selector)
                                    await asyncio.sleep(random.uniform(1, 3))
                                    break
                        except Exception:
                            pass  # Continue anyway
                        
                        # Wait for page to potentially update
                        await asyncio.sleep(random.uniform(2, 4))
                        
                        # Get updated content
                        page_content = await page.content()
                
                # Final realistic scrolling behavior if enabled
                if self.config.processing_config.simulate_human_behavior:
                    await page.mouse.wheel(0, random.randint(200, 400))
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    await page.mouse.wheel(0, -random.randint(100, 200))
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                
                # Get final page content
                html_content = page_content
                
                # Take screenshot
                screenshot_path = None
                if self.config.output_config.keep_screenshots:
                    screenshot_dir = self.config.output_config.screenshots_directory
                    screenshot_dir.mkdir(parents=True, exist_ok=True)
                    
                    filename = url.replace("https://", "").replace("http://", "").replace("/", "_")
                    screenshot_path = screenshot_dir / f"{filename}.png"
                    
                    await page.screenshot(path=str(screenshot_path), full_page=True)
                
                # Get load time
                load_time = (datetime.now() - start_time).total_seconds() * 1000
                
                await browser.close()
                
                return {
                    "success": True,
                    "html_content": html_content,
                    "screenshot_path": str(screenshot_path) if screenshot_path else None,
                    "load_time_ms": int(load_time),
                    "status_code": response.status if response else None,
                    "site_loads": True,
                    "error_message": None
                }
                
        except Exception as e:
            load_time = (datetime.now() - start_time).total_seconds() * 1000
            return {
                "success": False,
                "html_content": None,
                "screenshot_path": None,
                "load_time_ms": int(load_time),
                "status_code": None,
                "site_loads": False,
                "error_message": str(e)
            }


class WebScraperAgent:
    """Agno agent for web scraping operations."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.scraper_tool = WebScraperTool(config)
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are a web scraping specialist agent. Your role is to:
            1. Navigate to websites and extract content
            2. Take screenshots for visual analysis
            3. Detect if sites are blocked by bot protection
            4. Extract page metadata and loading performance
            5. Return structured data for further analysis
            
            Be thorough in your analysis and always provide detailed error information
            when sites cannot be accessed.
            """,
            markdown=True,
            show_tool_calls=True,
            monitoring=False  # Disable telemetry
        )
    
    async def scrape_site(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Scrape a website and update the analysis result."""
        logger.info("web_scraper_agent_started", url=url)
        
        try:
            # Use the scraper tool to get website data
            scrape_result = await self.scraper_tool.scrape_website(url)
            
            # Update the result object
            result.html_content = scrape_result["html_content"]
            result.screenshot_path = Path(scrape_result["screenshot_path"]) if scrape_result["screenshot_path"] else None
            result.load_time_ms = scrape_result["load_time_ms"]
            result.site_loads = scrape_result["site_loads"]
            result.error_message = scrape_result["error_message"]
            
            if scrape_result["success"]:
                result.status = AnalysisStatus.SUCCESS
                logger.info("web_scraper_agent_success", url=url, load_time_ms=result.load_time_ms)
            else:
                result.status = AnalysisStatus.FAILED
                logger.warning("web_scraper_agent_failed", url=url, error=result.error_message)
            
        except Exception as e:
            logger.error("web_scraper_agent_exception", url=url, error=str(e))
            result.status = AnalysisStatus.FAILED
            result.error_message = f"Web scraper agent error: {str(e)}"
        
        return result