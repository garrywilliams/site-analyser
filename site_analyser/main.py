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