"""Web scraping agent using Agno framework."""

import asyncio
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


class WebScraperTool:
    """Custom tool for web scraping with Playwright."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
    
    async def scrape_website(self, url: str) -> dict:
        """Scrape a website and return content and metadata."""
        start_time = datetime.now()
        
        try:
            async with async_playwright() as p:
                # Launch browser
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                
                page = await context.new_page()
                
                # Navigate to URL
                response = await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Get page content
                html_content = await page.content()
                
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