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
from .processors.ssl_checker import SSLProcessor
from .processors.web_scraper import WebScraperProcessor
from .processors.policy_analyzer import PolicyAnalyzerProcessor  
from .processors.trademark_analyzer import TrademarkAnalyzerProcessor
from .processors.bot_protection_detector import BotProtectionDetectorProcessor
from .utils.logging import setup_logging
from .utils.url_scraper import HMRCSoftwareListScraper
from .utils.rate_limiter import AIRateLimiter

load_dotenv()

logger = structlog.get_logger()


class SiteAnalyser:
    """Main site analysis orchestrator."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.job_id = str(uuid.uuid4())
        
        # Create shared rate limiter for AI requests
        self.ai_rate_limiter = AIRateLimiter(config.processing_config.ai_request_delay_seconds)
        
        # Initialize processors with shared rate limiter
        self.processors = [
            SSLProcessor(config),
            BotProtectionDetectorProcessor(config),  # Run early to detect access issues
            PolicyAnalyzerProcessor(config, self.ai_rate_limiter),
            TrademarkAnalyzerProcessor(config, self.ai_rate_limiter),
        ]
    
    async def analyze_sites(self) -> BatchJobResult:
        """Analyze all configured sites."""
        batch_result = BatchJobResult(
            job_id=self.job_id,
            started_at=datetime.now(timezone.utc),
            total_urls=len(self.config.urls),
            successful_analyses=0,
            failed_analyses=0
        )
        
        logger.info(
            "batch_job_started",
            job_id=self.job_id,
            total_urls=batch_result.total_urls,
            concurrent_requests=self.config.processing_config.concurrent_requests
        )
        
        # Ensure output directories exist
        self.config.output_config.results_directory.mkdir(parents=True, exist_ok=True)
        self.config.output_config.screenshots_directory.mkdir(parents=True, exist_ok=True)
        
        # Process URLs with concurrency control
        semaphore = asyncio.Semaphore(self.config.processing_config.concurrent_requests)
        
        async def analyze_single_site(url):
            async with semaphore:
                return await self._analyze_site(str(url))
        
        # Process all URLs concurrently
        tasks = [analyze_single_site(url) for url in self.config.urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error("site_analysis_exception", error=str(result))
                batch_result.failed_analyses += 1
            else:
                batch_result.results.append(result)
                if result.status == AnalysisStatus.SUCCESS:
                    batch_result.successful_analyses += 1
                else:
                    batch_result.failed_analyses += 1
        
        batch_result.completed_at = datetime.now(timezone.utc)
        
        # Save results
        await self._save_results(batch_result)
        
        logger.info(
            "batch_job_completed",
            job_id=self.job_id,
            total_urls=batch_result.total_urls,
            successful=batch_result.successful_analyses,
            failed=batch_result.failed_analyses,
            duration_seconds=(batch_result.completed_at - batch_result.started_at).total_seconds()
        )
        
        return batch_result
    
    async def _analyze_site(self, url: str) -> SiteAnalysisResult:
        """Analyze a single site through all processors."""
        start_time = datetime.now(timezone.utc)
        
        result = SiteAnalysisResult(
            url=url,
            timestamp=start_time,
            status=AnalysisStatus.SUCCESS,
            site_loads=False,
            processing_duration_ms=0
        )
        
        logger.info("site_analysis_started", url=url)
        
        # Use WebScraperProcessor with async context manager
        async with WebScraperProcessor(self.config) as web_scraper:
            result = await web_scraper.process_with_retry(url, result)
        
        # Process through other processors
        for processor in self.processors:
            result = await processor.process_with_retry(url, result)
        
        # Clean up resources if configured
        if not self.config.output_config.keep_html:
            result.html_content = None
        
        if not self.config.output_config.keep_screenshots and result.screenshot_path:
            try:
                result.screenshot_path.unlink()
                result.screenshot_path = None
            except Exception as e:
                logger.warning("screenshot_cleanup_failed", url=url, error=str(e))
        
        logger.info(
            "site_analysis_completed",
            url=url,
            status=result.status.value,
            site_loads=result.site_loads,
            has_ssl_analysis=bool(result.ssl_analysis),
            has_privacy_policy=bool(result.privacy_policy),
            has_terms_conditions=bool(result.terms_conditions),
            trademark_violations=len(result.trademark_violations),
            processing_duration_ms=result.processing_duration_ms
        )
        
        return result
    
    async def _save_results(self, batch_result: BatchJobResult) -> None:
        """Save batch results to JSON file."""
        if not self.config.output_config.json_output_file:
            return
        
        output_file = self.config.output_config.json_output_file
        output_data = batch_result.model_dump(mode="json")
        
        # Convert Path objects to strings for JSON serialization
        for result in output_data.get("results", []):
            if result.get("screenshot_path"):
                result["screenshot_path"] = str(result["screenshot_path"])
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        logger.info("results_saved", output_file=str(output_file))


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
@click.pass_context
def analyze(
    ctx,
    config: Optional[Path],
    urls: tuple[str, ...],
    urls_file: Optional[Path],
    output_dir: Path,
    concurrent_requests: int,
    ai_provider: str,
    ai_delay: float
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
        
        site_config = SiteAnalyserConfig(
            urls=url_list,
            ai_config=AIConfig(provider=ai_provider),
            processing_config=ProcessingConfig(
                concurrent_requests=concurrent_requests,
                ai_request_delay_seconds=ai_delay
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
@click.pass_context
def scrape_urls(ctx, source_url: str, output_file: Path, format: str):
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
            # Save as text file with URLs only
            unique_urls = scraper.get_unique_domains(entries)
            scraper.save_urls_to_file(entries, output_file)
            
            click.echo(f"✅ Saved {len(entries)} entries ({len(unique_urls)} unique domains) to {output_file}")
            
        elif format == 'json':
            # Save as JSON with full details
            import json
            json_output_file = output_file.with_suffix('.json')
            
            with open(json_output_file, 'w') as f:
                json.dump({
                    'source_url': source_url,
                    'scraped_at': datetime.now(timezone.utc).isoformat(),
                    'total_entries': len(entries),
                    'entries': entries
                }, f, indent=2)
            
            click.echo(f"✅ Saved detailed data to {json_output_file}")
        
        # Show some examples
        click.echo("\n📋 First few entries:")
        for entry in entries[:5]:
            click.echo(f"  • {entry['company_name']} - {entry['website_url']}")
        
        if len(entries) > 5:
            click.echo(f"  ... and {len(entries) - 5} more")
    
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
@click.pass_context
def scrape_and_analyze(ctx, source_url: str, output_dir: Path, concurrent_requests: int, ai_provider: str, ai_delay: float):
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
        
        site_config = SiteAnalyserConfig(
            urls=unique_urls,
            ai_config=AIConfig(provider=ai_provider),
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


if __name__ == "__main__":
    cli()