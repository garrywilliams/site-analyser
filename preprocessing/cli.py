#!/usr/bin/env python3
"""
Site Scraper CLI

Command-line interface for the site preprocessing scraper.
Handles URL input, configuration, and output management.
"""

import argparse
import asyncio
import uuid
from pathlib import Path
from typing import List

import structlog

from .scraper import SiteScraper, ScrapingConfig


async def async_main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Site Scraper - Capture screenshots and HTML from URLs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape URLs from command line
  python -m preprocessing.cli https://example.com https://test.com
  
  # Scrape URLs from file
  python -m preprocessing.cli --urls-file urls.txt
  
  # Custom output directory and job ID
  python -m preprocessing.cli --urls-file urls.txt --output-dir ./results --job-id my-job-123
  
  # Adjust viewport and concurrency
  python -m preprocessing.cli --urls-file urls.txt --viewport 1366x768 --max-concurrent 3
        """
    )
    
    # URL input options
    parser.add_argument('urls', nargs='*', 
                       help='URLs to scrape (space-separated)')
    parser.add_argument('--urls-file', type=Path,
                       help='Text file containing URLs (one per line)')
    
    # Output options
    parser.add_argument('--output-dir', type=Path, default=Path('./scraping_output'),
                       help='Output directory for screenshots and results (default: ./scraping_output)')
    parser.add_argument('--job-id', 
                       help='Job ID for this scraping run (default: auto-generated UUID)')
    
    # Scraping configuration
    parser.add_argument('--viewport', default='1920x1080',
                       help='Browser viewport size as WIDTHxHEIGHT (default: 1920x1080)')
    parser.add_argument('--timeout', type=int, default=30000,
                       help='Page load timeout in milliseconds (default: 30000)')
    parser.add_argument('--max-concurrent', type=int, default=5,
                       help='Maximum concurrent scraping tasks (default: 5)')
    parser.add_argument('--user-agent', 
                       default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                       help='Browser user agent string')
    
    # Output format options  
    parser.add_argument('--output-file',
                       help='Custom output file name for results JSON')
    
    args = parser.parse_args()
    
    # Set up structured logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logger = structlog.get_logger()
    
    try:
        # Parse viewport dimensions
        viewport_parts = args.viewport.split('x')
        if len(viewport_parts) != 2:
            raise ValueError("Viewport must be in format WIDTHxHEIGHT (e.g., 1920x1080)")
        viewport_width, viewport_height = map(int, viewport_parts)
        
        # Generate job ID if not provided
        job_id = args.job_id or str(uuid.uuid4())
        
        # Load URLs - validate that one source is provided
        if args.urls_file and args.urls:
            logger.error("cannot_specify_both", message="Cannot specify both --urls-file and command line URLs")
            return 1
        
        if args.urls_file:
            urls = SiteScraper.load_urls_from_file(args.urls_file)
        elif args.urls:
            urls = args.urls
        else:
            logger.error("no_urls_provided", message="Must specify URLs either via command line or --urls-file")
            return 1
        
        if not urls:
            logger.error("empty_url_list")
            return 1
        
        # Create configuration
        config = ScrapingConfig(
            job_id=job_id,
            output_dir=args.output_dir,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            timeout_ms=args.timeout,
            max_concurrent=args.max_concurrent,
            user_agent=args.user_agent
        )
        
        logger.info("starting_scraping_job",
                   job_id=job_id,
                   url_count=len(urls),
                   output_dir=str(args.output_dir),
                   viewport=args.viewport)
        
        # Execute scraping
        async with SiteScraper(config) as scraper:
            results = await scraper.scrape_urls(urls)
            
            # Save results
            output_file = None
            if args.output_file:
                output_file = args.output_dir / args.output_file
            
            results_path = scraper.save_results_json(output_file)
            
            # Print summary
            success_count = sum(1 for r in results if r.status == "success")
            timeout_count = sum(1 for r in results if r.status == "timeout")
            error_count = sum(1 for r in results if r.status == "error")
            
            print(f"\n✅ Scraping completed!")
            print(f"📊 Job ID: {job_id}")
            print(f"🌐 URLs processed: {len(urls)}")
            print(f"✅ Successful: {success_count}")
            print(f"⏱️  Timeouts: {timeout_count}")
            print(f"❌ Errors: {error_count}")
            print(f"📁 Output directory: {args.output_dir}")
            print(f"📄 Results saved to: {results_path}")
            
            if success_count > 0:
                screenshots_dir = args.output_dir / "screenshots" 
                print(f"📸 Screenshots saved to: {screenshots_dir}")
        
        return 0
        
    except Exception as e:
        logger.error("scraping_failed", error=str(e))
        return 1


def main():
    """Synchronous entry point for script usage."""
    return asyncio.run(async_main())


if __name__ == "__main__":
    exit(main())