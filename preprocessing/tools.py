#!/usr/bin/env python3
"""
Site Scraper Tool Functions

Agent-friendly wrapper functions around the core scraping functionality.
Designed for easy integration with Agno agents or other tool frameworks.
"""

import asyncio
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import structlog

from .scraper import SiteScraper, ScrapingConfig, ScrapingResult, SSLInfo

logger = structlog.get_logger()


async def scrape_websites(
    urls: Union[List[str], str],
    job_id: Optional[str] = None,
    output_dir: str = "./scraping_output",
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    timeout_ms: int = 30000,
    max_concurrent: int = 5,
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    save_screenshots: bool = True,
    return_html: bool = True
) -> Dict[str, Any]:
    """
    Scrape websites and return structured results.
    
    This function is designed to be easily callable by Agno agents or other tools.
    
    Args:
        urls: Single URL string or list of URL strings to scrape
        job_id: Optional job identifier (auto-generated if not provided)
        output_dir: Directory to save screenshots and results
        viewport_width: Browser viewport width in pixels
        viewport_height: Browser viewport height in pixels  
        timeout_ms: Page load timeout in milliseconds
        max_concurrent: Maximum concurrent scraping tasks
        user_agent: Browser user agent string
        save_screenshots: Whether to save screenshot files
        return_html: Whether to include full HTML in results
        
    Returns:
        Dict containing:
        - job_id: String identifier for this scraping job
        - summary: Dict with counts of successful/failed scrapes
        - results: List of scraping results for each URL
        - output_paths: Dict with paths to generated files
        
    Example:
        >>> result = await scrape_websites(["https://example.com", "https://test.org"])
        >>> print(f"Scraped {result['summary']['successful']} sites successfully")
    """
    try:
        # Normalize URLs to list
        if isinstance(urls, str):
            url_list = [urls]
        else:
            url_list = list(urls)
        
        if not url_list:
            return {
                "job_id": None,
                "success": False,
                "error": "No URLs provided",
                "summary": {"total": 0, "successful": 0, "failed": 0},
                "results": []
            }
        
        # Generate job ID if not provided
        if job_id is None:
            job_id = str(uuid.uuid4())
        
        # Create configuration
        config = ScrapingConfig(
            job_id=job_id,
            output_dir=Path(output_dir),
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            timeout_ms=timeout_ms,
            max_concurrent=max_concurrent,
            user_agent=user_agent
        )
        
        logger.info("tool_scraping_started", 
                   job_id=job_id,
                   url_count=len(url_list),
                   output_dir=output_dir)
        
        # Execute scraping
        async with SiteScraper(config) as scraper:
            raw_results = await scraper.scrape_urls(url_list)
            
            # Save results JSON
            results_path = scraper.save_results_json()
            
            # Convert results to tool-friendly format
            processed_results = []
            for result in raw_results:
                processed_result = _format_result_for_tool(
                    result, 
                    include_html=return_html, 
                    include_screenshot_path=save_screenshots,
                    scraper=scraper
                )
                processed_results.append(processed_result)
            
            # Generate summary
            successful = sum(1 for r in raw_results if r.status == "success")
            timeouts = sum(1 for r in raw_results if r.status == "timeout")
            errors = sum(1 for r in raw_results if r.status == "error")
            
            output_paths = {
                "results_json": str(results_path),
                "screenshots_dir": str(config.output_dir / "screenshots") if save_screenshots else None
            }
            
            return {
                "job_id": job_id,
                "success": True,
                "summary": {
                    "total": len(url_list),
                    "successful": successful,
                    "timeouts": timeouts, 
                    "errors": errors
                },
                "results": processed_results,
                "output_paths": output_paths,
                "execution_time_ms": sum(r.load_time_ms for r in raw_results)
            }
            
    except Exception as e:
        logger.error("tool_scraping_failed", error=str(e), job_id=job_id)
        return {
            "job_id": job_id,
            "success": False,
            "error": str(e),
            "summary": {"total": len(url_list) if 'url_list' in locals() else 0, 
                       "successful": 0, "failed": 1},
            "results": []
        }


def _format_result_for_tool(
    result: ScrapingResult, 
    include_html: bool = True,
    include_screenshot_path: bool = True,
    scraper: Optional[SiteScraper] = None
) -> Dict[str, Any]:
    """Format a ScrapingResult for tool consumption."""
    formatted = {
        "url": {
            "original": result.original_url,
            "final": result.final_url,
            "domain": result.domain,
            "redirected": result.redirected
        },
        "content": {
            "company_name": result.company_name,
            "html_size": result.html_size,
            "html_path": result.html_path,
        },
        "ssl": {
            "has_ssl": result.ssl_info.has_ssl,
            "is_valid": result.ssl_info.is_valid,
            "issuer": result.ssl_info.issuer,
            "subject": result.ssl_info.subject,
            "expires_date": result.ssl_info.expires_date,
            "days_until_expiry": result.ssl_info.days_until_expiry,
            "certificate_error": result.ssl_info.certificate_error
        },
        "bot_protection": {
            "detected": result.bot_protection.detected,
            "protection_type": result.bot_protection.protection_type,
            "indicators": result.bot_protection.indicators,
            "confidence": result.bot_protection.confidence
        },
        "performance": {
            "load_time_ms": result.load_time_ms,
            "viewport_size": result.viewport_size
        },
        "status": {
            "status": result.status,
            "error_message": result.error_message,
            "timestamp": result.timestamp
        }
    }
    
    # Conditionally include heavy data
    if include_html and result.html_path and scraper:
        try:
            html_content = scraper.load_html_content(result)
            formatted["content"]["html_content"] = html_content
        except Exception as e:
            formatted["content"]["html_load_error"] = str(e)
    
    if include_screenshot_path and result.screenshot_path:
        formatted["content"]["screenshot_path"] = result.screenshot_path
        formatted["content"]["screenshot_hash"] = result.screenshot_hash
    
    return formatted


async def check_ssl_certificates(urls: Union[List[str], str]) -> Dict[str, Any]:
    """
    Check SSL certificates for a list of URLs without full scraping.
    
    Lightweight function focused only on SSL certificate analysis.
    
    Args:
        urls: Single URL string or list of URL strings to check
        
    Returns:
        Dict containing SSL information for each URL
    """
    try:
        # Normalize URLs to list
        if isinstance(urls, str):
            url_list = [urls]
        else:
            url_list = list(urls)
        
        if not url_list:
            return {
                "success": False,
                "error": "No URLs provided",
                "results": []
            }
        
        # Create a temporary scraper just for SSL checking
        config = ScrapingConfig(
            job_id="ssl-check",
            output_dir=Path("/tmp/ssl-check")  # Won't be used
        )
        
        scraper = SiteScraper(config)
        results = []
        
        for url in url_list:
            try:
                ssl_info = await scraper.check_ssl_certificate(url)
                results.append({
                    "url": url,
                    "ssl": {
                        "has_ssl": ssl_info.has_ssl,
                        "is_valid": ssl_info.is_valid,
                        "issuer": ssl_info.issuer,
                        "subject": ssl_info.subject,
                        "expires_date": ssl_info.expires_date,
                        "days_until_expiry": ssl_info.days_until_expiry,
                        "certificate_error": ssl_info.certificate_error
                    }
                })
            except Exception as e:
                results.append({
                    "url": url,
                    "ssl": {
                        "has_ssl": False,
                        "is_valid": False,
                        "certificate_error": str(e)
                    }
                })
        
        return {
            "success": True,
            "results": results,
            "summary": {
                "total": len(url_list),
                "with_ssl": sum(1 for r in results if r["ssl"]["has_ssl"]),
                "valid_ssl": sum(1 for r in results if r["ssl"]["is_valid"]),
                "expiring_soon": sum(1 for r in results 
                                   if r["ssl"].get("days_until_expiry", 999) < 30)
            }
        }
        
    except Exception as e:
        logger.error("ssl_check_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "results": []
        }


def load_urls_from_file(file_path: str) -> Dict[str, Any]:
    """
    Load URLs from a text file.
    
    Tool-friendly wrapper around the file loading functionality.
    
    Args:
        file_path: Path to text file containing URLs (one per line)
        
    Returns:
        Dict containing loaded URLs and metadata
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "urls": []
            }
        
        urls = SiteScraper.load_urls_from_file(path)
        
        return {
            "success": True,
            "urls": urls,
            "count": len(urls),
            "source_file": str(path.absolute())
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "urls": []
        }


# Tool function registry for easy discovery
AVAILABLE_TOOLS = {
    "scrape_websites": {
        "function": scrape_websites,
        "description": "Capture screenshots, HTML content, and SSL info from websites",
        "async": True,
        "parameters": {
            "urls": "List of URLs or single URL string",
            "job_id": "Optional job identifier",
            "output_dir": "Directory for output files",
            "viewport_width": "Browser width in pixels (default: 1920)",
            "viewport_height": "Browser height in pixels (default: 1080)", 
            "timeout_ms": "Page load timeout in milliseconds (default: 30000)",
            "max_concurrent": "Max concurrent requests (default: 5)",
            "save_screenshots": "Whether to save screenshot files (default: True)",
            "return_html": "Whether to include HTML in results (default: True)"
        }
    },
    "check_ssl_certificates": {
        "function": check_ssl_certificates,
        "description": "Check SSL certificate information for URLs",
        "async": True,
        "parameters": {
            "urls": "List of URLs or single URL string"
        }
    },
    "load_urls_from_file": {
        "function": load_urls_from_file,
        "description": "Load URLs from a text file",
        "async": False,
        "parameters": {
            "file_path": "Path to text file with URLs"
        }
    }
}