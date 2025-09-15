"""Main entry point for the Site Analyser application."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
import structlog
from dotenv import load_dotenv

from .models.analysis import SiteAnalysisResult, BatchJobResult, AnalysisStatus
from .models.config import SiteAnalyserConfig
from .agents.coordinator import SiteAnalysisCoordinator
from .utils.logging import setup_logging
from .utils.url_scraper import HMRCSoftwareListScraper

load_dotenv()

logger = structlog.get_logger()


class SiteAnalyser:
    """Main site analysis orchestrator using Agno multi-agent framework."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.coordinator = SiteAnalysisCoordinator(config)
    
    async def analyze_sites(self) -> BatchJobResult:
        """Analyze all configured sites using the Agno coordinator."""
        return await self.coordinator.analyze_sites()


@click.group()
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_context
def cli(ctx, debug: bool):
    """Analyze websites for compliance and trademark violations."""
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug
    setup_logging(debug=debug)


@cli.command()
@click.option(
    '--config', '-c',
    type=click.Path(exists=True, path_type=Path),
    help='Path to configuration file'
)
@click.option(
    '--urls',
    multiple=True,
    help='URLs to analyze (can be specified multiple times)'
)
@click.option(
    '--urls-file',
    type=click.Path(exists=True, path_type=Path),
    help='Text file containing URLs to analyze (one per line)'
)
@click.option(
    '--output-dir', '-o',
    type=click.Path(path_type=Path),
    default=Path('./results'),
    help='Output directory for results'
)
@click.option(
    '--concurrent-requests', '-j',
    type=int,
    default=5,
    help='Number of concurrent requests'
)
@click.option(
    '--ai-provider',
    type=click.Choice(['openai', 'anthropic']),
    default='openai',
    help='AI provider for image analysis'
)
@click.option(
    '--ai-delay',
    type=float,
    default=1.5,
    help='Delay between AI API requests in seconds (to avoid rate limits)'
)
@click.option(
    '--ai-base-url',
    type=str,
    help='Custom base URL for OpenAI-compatible APIs (e.g., your local proxy)'
)
@click.option(
    '--stealth/--no-stealth',
    default=True,
    help='Enable/disable bot detection evasion techniques'
)
@click.option(
    '--random-agents/--no-random-agents',
    default=True,
    help='Use random realistic user agents'
)
@click.option(
    '--human-behavior/--no-human-behavior',
    default=True,
    help='Simulate human-like mouse movements and delays'
)
@click.option(
    '--handle-captcha/--no-handle-captcha',
    default=True,
    help='Attempt to handle basic CAPTCHA challenges'
)
@click.pass_context
def analyze(
    ctx,
    config: Optional[Path],
    urls: tuple[str, ...],
    urls_file: Optional[Path],
    output_dir: Path,
    concurrent_requests: int,
    ai_provider: str,
    ai_delay: float,
    ai_base_url: Optional[str],
    stealth: bool,
    random_agents: bool,
    human_behavior: bool,
    handle_captcha: bool
):
    """Analyze websites for compliance and trademark violations."""
    debug = ctx.obj.get('debug', False)
    
    # Collect URLs from various sources
    url_list = list(urls) if urls else []
    
    # Load URLs from file if provided
    if urls_file:
        with open(urls_file, 'r') as f:
            file_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            url_list.extend(file_urls)
    
    # Load configuration
    if config:
        site_config = SiteAnalyserConfig.model_validate_json(config.read_text())
        # Override URLs if provided via command line
        if url_list:
            site_config.urls = url_list
    else:
        if not url_list:
            raise click.ClickException("Either --config, --urls, or --urls-file must be provided")
        
        from .models.config import AIConfig, ProcessingConfig, OutputConfig
        
        ai_config_kwargs = {"provider": ai_provider}
        if ai_base_url:
            ai_config_kwargs["base_url"] = ai_base_url
        
        site_config = SiteAnalyserConfig(
            urls=url_list,
            ai_config=AIConfig(**ai_config_kwargs),
            processing_config=ProcessingConfig(
                concurrent_requests=concurrent_requests,
                ai_request_delay_seconds=ai_delay,
                use_stealth_mode=stealth,
                random_user_agents=random_agents,
                simulate_human_behavior=human_behavior,
                handle_captcha_challenges=handle_captcha
            ),
            output_config=OutputConfig(
                results_directory=output_dir,
                screenshots_directory=output_dir / "screenshots",
                json_output_file=output_dir / "analysis_results.json"
            )
        )
    
    # Run analysis
    analyzer = SiteAnalyser(site_config)
    batch_result = asyncio.run(analyzer.analyze_sites())
    
    # Print summary
    click.echo(f"\nAnalysis completed!")
    click.echo(f"Job ID: {batch_result.job_id}")
    click.echo(f"Total URLs: {batch_result.total_urls}")
    click.echo(f"Successful: {batch_result.successful_analyses}")
    click.echo(f"Failed: {batch_result.failed_analyses}")
    
    high_confidence_violations = sum(
        len([v for v in result.trademark_violations if v.confidence >= 0.8])
        for result in batch_result.results
    )
    if high_confidence_violations > 0:
        click.echo(f"⚠️  High-confidence trademark violations found: {high_confidence_violations}")


@cli.command()
@click.option(
    '--source-url',
    default='https://www.tax.service.gov.uk/making-tax-digital-software/',
    help='URL of HMRC software list page to scrape'
)
@click.option(
    '--output-file', '-o',
    type=click.Path(path_type=Path),
    default=Path('./hmrc-software-urls.txt'),
    help='Output file for scraped URLs'
)
@click.option(
    '--format',
    type=click.Choice(['txt', 'json']),
    default='txt',
    help='Output format for scraped URLs'
)
@click.option(
    '--minimal',
    is_flag=True,
    help='Output only URLs, one per line (no comments or metadata)'
)
@click.pass_context
def scrape_urls(ctx, source_url: str, output_file: Path, format: str, minimal: bool):
    """Scrape vendor URLs from HMRC Making Tax Digital software list."""
    debug = ctx.obj.get('debug', False)
    
    async def scrape():
        scraper = HMRCSoftwareListScraper()
        
        click.echo(f"Scraping software URLs from: {source_url}")
        entries = await scraper.scrape_software_urls(source_url)
        
        if not entries:
            click.echo("⚠️  No software entries found!")
            return
        
        click.echo(f"Found {len(entries)} software entries")
        
        if format == 'txt':
            unique_urls = scraper.get_unique_domains(entries)
            
            if minimal:
                # Save only URLs, one per line
                scraper.save_urls_minimal(entries, output_file)
                click.echo(f"✅ Saved {len(unique_urls)} unique URLs to {output_file}")
            else:
                # Save as text file with comments and metadata
                scraper.save_urls_to_file(entries, output_file)
                click.echo(f"✅ Saved {len(entries)} entries ({len(unique_urls)} unique domains) to {output_file}")
            
        elif format == 'json':
            json_output_file = output_file.with_suffix('.json')
            unique_urls = scraper.get_unique_domains(entries)
            
            if minimal:
                # Save minimal JSON with just URLs
                import json
                with open(json_output_file, 'w') as f:
                    json.dump({
                        'source_url': source_url,
                        'scraped_at': datetime.now(timezone.utc).isoformat(),
                        'total_unique_urls': len(unique_urls),
                        'urls': unique_urls
                    }, f, indent=2)
                click.echo(f"✅ Saved {len(unique_urls)} unique URLs to {json_output_file}")
            else:
                # Save as JSON with full details
                import json
                with open(json_output_file, 'w') as f:
                    json.dump({
                        'source_url': source_url,
                        'scraped_at': datetime.now(timezone.utc).isoformat(),
                        'total_entries': len(entries),
                        'entries': entries
                    }, f, indent=2)
                click.echo(f"✅ Saved detailed data to {json_output_file}")
        
        # Show some examples (skip if minimal mode)
        if not minimal:
            click.echo("\n📋 First few entries:")
            for entry in entries[:5]:
                click.echo(f"  • {entry['company_name']} - {entry['website_url']}")
            
            if len(entries) > 5:
                click.echo(f"  ... and {len(entries) - 5} more")
        else:
            # Show just first few URLs in minimal mode
            unique_urls = scraper.get_unique_domains(entries)
            click.echo(f"\n📋 First few URLs:")
            for url in unique_urls[:5]:
                click.echo(f"  • {url}")
            
            if len(unique_urls) > 5:
                click.echo(f"  ... and {len(unique_urls) - 5} more")
    
    asyncio.run(scrape())


@cli.command()
@click.option(
    '--source-url',
    default='https://www.tax.service.gov.uk/making-tax-digital-software/',
    help='URL to scrape for vendor URLs'
)
@click.option(
    '--output-dir', '-o',
    type=click.Path(path_type=Path),
    default=Path('./results'),
    help='Output directory for results'
)
@click.option(
    '--concurrent-requests', '-j',
    type=int,
    default=3,
    help='Number of concurrent requests (lower for politeness)'
)
@click.option(
    '--ai-provider',
    type=click.Choice(['openai', 'anthropic']),
    default='openai',
    help='AI provider for image analysis'
)
@click.option(
    '--ai-delay',
    type=float,
    default=2.0,
    help='Delay between AI API requests in seconds (higher for bulk processing)'
)
@click.option(
    '--ai-base-url',
    type=str,
    help='Custom base URL for OpenAI-compatible APIs (e.g., your local proxy)'
)
@click.pass_context
def scrape_and_analyze(ctx, source_url: str, output_dir: Path, concurrent_requests: int, ai_provider: str, ai_delay: float, ai_base_url: Optional[str]):
    """Scrape HMRC software list and analyze all vendor websites."""
    debug = ctx.obj.get('debug', False)
    
    async def scrape_then_analyze():
        # First, scrape the URLs
        click.echo(f"🔍 Scraping vendor URLs from: {source_url}")
        scraper = HMRCSoftwareListScraper()
        entries = await scraper.scrape_software_urls(source_url)
        
        if not entries:
            click.echo("❌ No URLs found to analyze!")
            return
        
        # Get unique domains to analyze
        unique_urls = scraper.get_unique_domains(entries)
        click.echo(f"📊 Found {len(unique_urls)} unique vendor websites")
        
        # Save the scraped URLs for reference
        urls_file = output_dir / "scraped-hmrc-urls.txt"
        scraper.save_urls_to_file(entries, urls_file)
        
        # Create configuration for analysis
        from .models.config import AIConfig, ProcessingConfig, OutputConfig
        
        ai_config_kwargs = {"provider": ai_provider}
        if ai_base_url:
            ai_config_kwargs["base_url"] = ai_base_url
        
        site_config = SiteAnalyserConfig(
            urls=unique_urls,
            ai_config=AIConfig(**ai_config_kwargs),
            processing_config=ProcessingConfig(
                concurrent_requests=concurrent_requests,
                ai_request_delay_seconds=ai_delay
            ),
            output_config=OutputConfig(
                results_directory=output_dir,
                screenshots_directory=output_dir / "screenshots",
                json_output_file=output_dir / "hmrc_vendor_analysis.json"
            )
        )
        
        # Run the analysis
        click.echo(f"🚀 Starting analysis of {len(unique_urls)} websites...")
        analyzer = SiteAnalyser(site_config)
        batch_result = await analyzer.analyze_sites()
        
        # Print summary
        click.echo(f"\n✅ Analysis completed!")
        click.echo(f"📈 Results:")
        click.echo(f"   • Total websites: {batch_result.total_urls}")
        click.echo(f"   • Successful: {batch_result.successful_analyses}")
        click.echo(f"   • Failed: {batch_result.failed_analyses}")
        
        # Check for trademark violations
        high_confidence_violations = sum(
            len([v for v in result.trademark_violations if v.confidence >= 0.8])
            for result in batch_result.results
        )
        if high_confidence_violations > 0:
            click.echo(f"⚠️  High-confidence trademark violations: {high_confidence_violations}")
    
    asyncio.run(scrape_then_analyze())


@cli.command()
@click.option(
    '--urls',
    multiple=True,
    help='URLs to capture screenshots for (can be specified multiple times)'
)
@click.option(
    '--urls-file',
    type=click.Path(exists=True, path_type=Path),
    help='Text file containing URLs to screenshot (one per line)'
)
@click.option(
    '--output-dir', '-o',
    type=click.Path(path_type=Path),
    default=Path('./screenshots'),
    help='Output directory for screenshots'
)
@click.option(
    '--concurrent-requests', '-j',
    type=int,
    default=5,
    help='Number of concurrent screenshot captures'
)
@click.option(
    '--timeout',
    type=int,
    default=15,
    help='Screenshot timeout in seconds'
)
@click.option(
    '--viewport-width',
    type=int,
    default=1920,
    help='Browser viewport width for screenshots'
)
@click.option(
    '--viewport-height',
    type=int,
    default=1080,
    help='Browser viewport height for screenshots'
)
@click.option(
    '--stealth/--no-stealth',
    default=True,
    help='Enable/disable bot detection evasion techniques'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Enable verbose logging output'
)
@click.pass_context
def screenshot(
    ctx,
    urls: tuple[str, ...],
    urls_file: Optional[Path],
    output_dir: Path,
    concurrent_requests: int,
    timeout: int,
    viewport_width: int,
    viewport_height: int,
    stealth: bool,
    verbose: bool
):
    """Capture screenshots of websites using Playwright (no AI analysis)."""
    debug = ctx.obj.get('debug', False) or verbose
    
    # Set up logging level based on verbose flag
    if verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        click.echo(f"🔊 Verbose logging enabled")
    
    async def capture_screenshots():
        # Collect URLs from various sources
        url_list = list(urls) if urls else []
        
        # Load URLs from file if provided
        if urls_file:
            with open(urls_file, 'r') as f:
                file_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                url_list.extend(file_urls)
        
        if not url_list:
            raise click.ClickException("Either --urls or --urls-file must be provided")
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup configuration for web scraping only
        from .models.config import SiteAnalyserConfig, ProcessingConfig, OutputConfig
        
        config = SiteAnalyserConfig(
            urls=url_list,
            processing_config=ProcessingConfig(
                concurrent_requests=concurrent_requests,
                screenshot_timeout_seconds=timeout,
                use_stealth_mode=stealth,
                viewport_width=viewport_width,
                viewport_height=viewport_height
            ),
            output_config=OutputConfig(
                results_directory=output_dir,
                screenshots_directory=output_dir,
                json_output_file=output_dir / "screenshot_results.json"
            )
        )
        
        # Import and use web scraper processor directly
        from .processors.web_scraper import WebScraperProcessor
        from .models.analysis import SiteAnalysisResult, AnalysisStatus
        from datetime import datetime
        
        click.echo(f"🖼️  Capturing screenshots for {len(url_list)} URLs...")
        click.echo(f"📁 Output directory: {output_dir.absolute()}")
        click.echo(f"⚙️  Viewport: {viewport_width}x{viewport_height}")
        click.echo(f"⏱️  Timeout: {timeout}s per URL")
        click.echo(f"🔧 Concurrent requests: {concurrent_requests}")
        click.echo(f"🔍 Debug mode: {debug}")
        click.echo(f"📋 URLs to process:")
        for i, url in enumerate(url_list, 1):
            click.echo(f"   {i}. {url}")
        
        results = []
        semaphore = asyncio.Semaphore(concurrent_requests)
        
        async def capture_single_screenshot(url: str):
            async with semaphore:
                try:
                    click.echo(f"🚀 Starting screenshot capture for: {url}")
                    
                    async with WebScraperProcessor(config) as processor:
                        click.echo(f"📱 Browser initialized for: {url}")
                        
                        # Create initial result
                        result = SiteAnalysisResult(
                            url=url,
                            timestamp=datetime.now(),
                            status=AnalysisStatus.SUCCESS,
                            site_loads=True,
                            processing_duration_ms=0
                        )
                        
                        # Process the screenshot
                        result = await processor.process(url, result)
                        
                        if result.screenshot_path:
                            click.echo(f"📸 Screenshot saved: {result.screenshot_path}")
                            click.echo(f"📍 Full path: {result.screenshot_path.absolute()}")
                        else:
                            click.echo(f"❌ No screenshot path set for: {url}")
                        
                        return result
                        
                except Exception as e:
                    click.echo(f"💥 Exception in capture_single_screenshot for {url}: {e}")
                    import traceback
                    click.echo(f"🔍 Traceback: {traceback.format_exc()}")
                    return e
        
        # Process all URLs concurrently
        tasks = [capture_single_screenshot(url) for url in url_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and show summary
        successful = 0
        failed = 0
        
        for i, result in enumerate(results):
            url = url_list[i]
            if isinstance(result, Exception):
                click.echo(f"❌ {url}: {result}")
                failed += 1
            elif result.site_loads and result.screenshot_path:
                click.echo(f"✅ {url}: {result.screenshot_path.name}")
                successful += 1
            else:
                click.echo(f"⚠️  {url}: {result.error_message or 'Screenshot failed'}")
                failed += 1
        
        # Save results summary
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_urls": len(url_list),
            "successful": successful,
            "failed": failed,
            "urls": url_list,
            "output_directory": str(output_dir),
            "viewport": f"{viewport_width}x{viewport_height}",
            "timeout_seconds": timeout
        }
        
        import json
        with open(output_dir / "screenshot_results.json", 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Final summary
        click.echo(f"\n📊 Screenshot capture completed!")
        click.echo(f"✅ Successful: {successful}")
        click.echo(f"❌ Failed: {failed}")
        click.echo(f"📁 Screenshots saved to: {output_dir}")
    
    asyncio.run(capture_screenshots())


if __name__ == "__main__":
    cli()