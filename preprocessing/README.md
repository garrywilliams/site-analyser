# Site Scraper - Preprocessing Module

A robust website preprocessing tool that captures screenshots, HTML content, and SSL certificate information from a list of URLs. Designed for batch processing with comprehensive error handling and structured output.

## Features

- 📸 **Screenshot Capture** - Full-page screenshots with configurable viewport
- 📄 **HTML Content Extraction** - Complete page HTML after JavaScript execution
- 🔄 **Redirect Handling** - Tracks and follows redirects automatically
- 🏢 **Company Name Detection** - Extracts company names using multiple methods
- 🔒 **SSL Certificate Analysis** - Validates HTTPS and captures certificate details
- 🚀 **Concurrent Processing** - Configurable concurrency with rate limiting
- 📊 **Structured Output** - JSON results with comprehensive metadata
- 🎯 **Deduplication** - SHA-256 hashing for screenshot deduplication
- ⏱️ **Timeout Handling** - Robust error handling and retry logic

## Installation

```bash
# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install chromium
```

## Quick Start

```bash
# Scrape URLs from command line
uv run python -m preprocessing https://example.com https://test.com

# Scrape URLs from file
uv run python -m preprocessing --urls-file example-urls.txt

# Using the installed script
uv run site-scraper --urls-file urls.txt
```

## Usage Examples

### Basic Usage

```bash
# Single URL
uv run python -m preprocessing https://example.com

# Multiple URLs
uv run python -m preprocessing https://example.com https://google.com https://github.com

# URLs from file
uv run python -m preprocessing --urls-file my-urls.txt
```

### Advanced Configuration

```bash
# Custom output directory and job ID
uv run python -m preprocessing \
  --urls-file urls.txt \
  --output-dir ./results \
  --job-id my-batch-2025

# Adjust viewport and performance settings
uv run python -m preprocessing \
  --urls-file urls.txt \
  --viewport 1366x768 \
  --timeout 20000 \
  --max-concurrent 3

# Custom user agent
uv run python -m preprocessing \
  --urls-file urls.txt \
  --user-agent "MyBot/1.0"
```

## Command Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `urls` | - | URLs to scrape (space-separated) |
| `--urls-file` | - | Text file with URLs (one per line) |
| `--output-dir` | `./scraping_output` | Output directory for results |
| `--job-id` | auto-generated | Custom job ID for this run |
| `--viewport` | `1920x1080` | Browser viewport (WIDTHxHEIGHT) |
| `--timeout` | `30000` | Page load timeout (milliseconds) |
| `--max-concurrent` | `5` | Maximum concurrent tasks |
| `--user-agent` | Standard Chrome | Browser user agent string |
| `--output-file` | auto-generated | Custom output filename |

## URL Input Format

Create a text file with one URL per line:

```text
# My website list - comments start with #
https://example.com
http://test.org  # This will redirect to HTTPS
https://mysite.co.uk
```

## Output Structure

### Directory Layout
```
scraping_output/
├── screenshots/
│   ├── job-id_example.com_timestamp.png
│   └── job-id_google.com_timestamp.png
├── html/
│   ├── job-id_example.com_timestamp.html
│   └── job-id_google.com_timestamp.html
└── job-id_scraping_results.json
```

### JSON Output Format

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2025-01-17T10:30:00.123456",
  "config": {
    "viewport_size": "1920x1080",
    "timeout_ms": 30000,
    "max_concurrent": 5
  },
  "summary": {
    "total_urls": 4,
    "successful": 3,
    "timeouts": 1,
    "errors": 0
  },
  "results": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "original_url": "http://example.com",
      "final_url": "https://example.com/",
      "domain": "example.com",
      "company_name": "Example Corporation",
      "html_path": "html/job-id_example.com_123456.html",
      "html_size": 45678,
      "screenshot_path": "screenshots/job-id_example.com_123456.png",
      "screenshot_hash": "a1b2c3d4e5f6...",
      "load_time_ms": 1234,
      "viewport_size": "1920x1080",
      "redirected": true,
      "ssl_info": {
        "has_ssl": true,
        "is_valid": true,
        "issuer": "Let's Encrypt Authority X3",
        "subject": "example.com",
        "expires_date": "2025-06-15T23:59:59Z",
        "days_until_expiry": 149,
        "certificate_error": null
      },
      "status": "success",
      "error_message": null,
      "timestamp": "2025-01-17T10:30:01.234567"
    }
  ]
}
```

## SSL Certificate Information

The scraper automatically analyzes SSL certificates for HTTPS sites:

- **has_ssl**: Whether the site uses HTTPS
- **is_valid**: Whether the certificate is valid and trusted
- **issuer**: Certificate authority that issued the cert
- **subject**: Domain(s) the certificate covers
- **expires_date**: Certificate expiration date (ISO format)
- **days_until_expiry**: Days remaining until expiration
- **certificate_error**: Details if certificate validation fails

## HTML Content Management

To keep JSON result files manageable, HTML content is saved to separate files:

- **HTML files**: Saved to `html/job-id_domain_timestamp.html`
- **JSON reference**: Contains `html_path` and `html_size` instead of full content
- **On-demand loading**: Use the scraper's `load_html_content()` method when needed

```python
from preprocessing import SiteScraper, ScrapingConfig
from pathlib import Path

# Load results and access HTML when needed
config = ScrapingConfig(job_id="existing-job", output_dir=Path("./results"))
scraper = SiteScraper(config)

# Assuming you have a result from the JSON
html_content = scraper.load_html_content(result)
```

## Company Name Detection

The scraper tries multiple methods to extract company names:

1. **OpenGraph meta tags** - `og:site_name` property
2. **HTML title tag** - Cleaned of common suffixes like "- Home"
3. **First H1 heading** - Main page heading
4. **Domain fallback** - Cleaned domain name if other methods fail

## Error Handling

The scraper handles various scenarios gracefully:

- **Timeouts**: Pages that take too long to load
- **Network errors**: Connection failures, DNS issues
- **SSL errors**: Invalid or expired certificates (still captures info)
- **JavaScript errors**: Page rendering issues
- **Invalid URLs**: Malformed or unreachable URLs

Each failed URL still produces a result with error information.

## Performance Tuning

### Concurrency Settings

- **Low bandwidth**: `--max-concurrent 2`
- **Standard usage**: `--max-concurrent 5` (default)
- **High-performance**: `--max-concurrent 10`

### Timeout Settings

- **Fast sites**: `--timeout 15000` (15 seconds)
- **Standard**: `--timeout 30000` (30 seconds, default)
- **Slow sites**: `--timeout 60000` (60 seconds)

### Viewport Settings

- **Mobile**: `--viewport 375x667`
- **Tablet**: `--viewport 768x1024` 
- **Desktop**: `--viewport 1920x1080` (default)
- **High-DPI**: `--viewport 2560x1440`

## Integration

The output JSON format is designed to integrate with database loading tools and analysis pipelines. Each result contains all necessary metadata for compliance monitoring and analysis workflows.

## Error Codes

- **success**: Screenshot and HTML captured successfully
- **timeout**: Page load exceeded timeout limit
- **error**: Network, SSL, or other technical error occurred

All results include detailed error messages when applicable.

## Best Practices

1. **Test with small batches** first to validate URLs
2. **Use appropriate concurrency** for your network and target sites
3. **Monitor timeout settings** based on target site performance
4. **Check SSL certificate expiry** for compliance monitoring
5. **Review error messages** to identify systematic issues

## Examples

### Government Site Monitoring
```bash
# Monitor gov.uk sites with longer timeouts
uv run python -m preprocessing \
  --urls-file government-sites.txt \
  --job-id gov-compliance-2025-01 \
  --timeout 45000 \
  --viewport 1920x1080
```

### Mobile Site Testing
```bash
# Test mobile responsiveness
uv run python -m preprocessing \
  --urls-file mobile-sites.txt \
  --viewport 375x667 \
  --job-id mobile-test-batch
```

### High-Volume Processing
```bash
# Process large URL lists efficiently
uv run python -m preprocessing \
  --urls-file large-list.txt \
  --max-concurrent 8 \
  --timeout 20000 \
  --job-id bulk-analysis-$(date +%Y%m%d)
```

## Tool Functions for Agent Integration

The preprocessing module includes agent-friendly tool functions designed for easy integration with Agno agents or other automation frameworks.

### Available Tool Functions

#### `scrape_websites(urls, **options)`
Full website scraping with screenshots, HTML content, and SSL analysis.

```python
from preprocessing.tools import scrape_websites

# Scrape multiple sites
result = await scrape_websites([
    "https://example.com", 
    "https://github.com"
], job_id="my-analysis", timeout_ms=20000)

# Check results
if result['success']:
    print(f"Scraped {result['summary']['successful']} sites")
    for site_result in result['results']:
        print(f"Company: {site_result['content']['company_name']}")
        print(f"SSL valid: {site_result['ssl']['is_valid']}")
```

#### `check_ssl_certificates(urls)`
Lightweight SSL certificate checking without full scraping.

```python
from preprocessing.tools import check_ssl_certificates

# Quick SSL check
result = await check_ssl_certificates([
    "https://example.com",
    "https://expired-cert-site.com"
])

print(f"SSL Summary: {result['summary']}")
for site in result['results']:
    ssl_info = site['ssl']
    if ssl_info['days_until_expiry'] and ssl_info['days_until_expiry'] < 30:
        print(f"⚠️ {site['url']} expires soon!")
```

#### `load_urls_from_file(file_path)`
Load URLs from text files.

```python
from preprocessing.tools import load_urls_from_file

# Load URLs from file
result = load_urls_from_file("my-urls.txt")
if result['success']:
    urls = result['urls']
    print(f"Loaded {len(urls)} URLs")
```

### Tool Function Response Format

All tool functions return structured responses:

```python
{
    "success": True,          # Operation succeeded
    "job_id": "uuid-string",  # Job identifier (scraping only)
    "summary": {              # High-level statistics
        "total": 5,
        "successful": 4,
        "errors": 1
    },
    "results": [...],         # Detailed results array
    "output_paths": {         # File paths (scraping only)
        "results_json": "path/to/results.json",
        "screenshots_dir": "path/to/screenshots/"
    }
}
```

### Error Handling

Tool functions handle errors gracefully and always return structured responses:

```python
{
    "success": False,
    "error": "Description of what went wrong",
    "results": []
}
```

### Integration Example

```python
# Example of how an Agno agent might use these tools
import asyncio
from preprocessing.tools import scrape_websites, check_ssl_certificates

async def analyze_competitor_sites(urls):
    """Agent function to analyze competitor websites."""
    
    # Step 1: Quick SSL check to prioritize secure sites
    ssl_results = await check_ssl_certificates(urls)
    secure_sites = [
        r['url'] for r in ssl_results['results'] 
        if r['ssl']['is_valid']
    ]
    
    # Step 2: Full scraping of secure sites only
    if secure_sites:
        scrape_results = await scrape_websites(
            secure_sites,
            job_id="competitor-analysis",
            timeout_ms=25000,
            return_html=False  # Skip HTML if not needed
        )
        
        # Step 3: Extract insights
        insights = []
        for result in scrape_results['results']:
            if result['status']['status'] == 'success':
                insights.append({
                    'company': result['content']['company_name'],
                    'domain': result['url']['domain'],
                    'ssl_expires': result['ssl']['days_until_expiry'],
                    'load_time': result['performance']['load_time_ms']
                })
        
        return {
            'analysis_complete': True,
            'sites_analyzed': len(insights),
            'insights': insights
        }
    
    return {'analysis_complete': False, 'reason': 'No secure sites found'}
```

### Tool Discovery

Tools are self-documenting via the `AVAILABLE_TOOLS` registry:

```python
from preprocessing.tools import AVAILABLE_TOOLS

# List available tools
for name, info in AVAILABLE_TOOLS.items():
    print(f"{name}: {info['description']}")
    print(f"Parameters: {info['parameters']}")
```

## Agno Agent Integration (Future-Ready)

The preprocessing module includes pre-built Agno tool wrappers for seamless agent integration. When you're ready to use Agno agents, the tools are already prepared with optimized defaults.

### Quick Start with Agno

```python
from agno.agent import Agent
from agno.models.openai import OpenAILike
from preprocessing import AGNO_TOOLS, AGNO_AVAILABLE

# Check if Agno integration is ready
if AGNO_AVAILABLE:
    # Create agent with preprocessing tools
    model = OpenAILike(id="gpt-4o-mini", api_key="...", base_url="...")
    agent = Agent(model=model, tools=AGNO_TOOLS)
    
    # Use the agent
    response = await agent.arun("""
    Analyze these competitor websites for security issues:
    - https://competitor1.com
    - https://competitor2.com
    
    Focus on SSL certificate status and expiry dates.
    """)
```

### Available Agno Tools

#### `scrape_websites` (Agno optimized)
- **Default**: `return_html=False` to reduce token usage
- **Always**: Saves screenshots and captures SSL info
- **Optimized**: For agent workflows with structured responses

#### `check_ssl_certificates` 
- **Lightweight**: SSL-only analysis without full scraping  
- **Perfect for**: Security audits and certificate monitoring

#### `load_urls_from_file`
- **Batch processing**: Load URLs from files for large-scale analysis
- **Comment support**: Lines starting with # are ignored

#### `quick_site_analysis` (New!)
- **Intelligent analysis** with configurable focus areas:
  - `focus="security"` - SSL certificates, HTTPS usage
  - `focus="performance"` - Load times, speed analysis  
  - `focus="content"` - Company names, HTML content
- **Smart filtering**: Analyzes only relevant sites based on focus
- **High-level insights**: Generates summaries and recommendations

### Agent Workflow Examples

#### Security Monitoring Agent
```python
response = await agent.arun("""
Check SSL certificates for these government contractor sites and flag any 
expiring within 30 days:
- https://contractor1.gov.uk  
- https://contractor2.co.uk
""")
```

#### Competitor Analysis Agent  
```python
response = await agent.arun("""
Perform a quick analysis of these competitor sites focusing on performance:
- https://competitor1.com
- https://competitor2.com

Identify which sites load fastest and might be using better hosting.
""")
```

#### Compliance Monitoring Agent
```python  
response = await agent.arun("""
Load URLs from compliance-check.txt and analyze them for:
1. SSL certificate validity and expiry
2. Company name extraction  
3. Screenshot capture for visual review

Focus on security aspects and flag any issues.
""")
```

### Tool Metadata

Each Agno tool includes rich metadata for intelligent tool selection:

```python
from preprocessing import TOOL_METADATA

for tool_name, metadata in TOOL_METADATA.items():
    print(f"{tool_name}:")
    print(f"  Category: {metadata['category']}")
    print(f"  Complexity: {metadata['complexity']}")  
    print(f"  Est. Time: {metadata['estimated_time']}")
```

### Future Migration Path

**Current Usage (Works Now):**
```python
from preprocessing.tools import scrape_websites
result = await scrape_websites(["https://example.com"])
```

**Future Agno Usage (When Ready):**
```python
from preprocessing import AGNO_TOOLS
agent = Agent(model=model, tools=AGNO_TOOLS)
await agent.arun("Scrape example.com and analyze its SSL certificate")
```

**No Code Changes Required** - The same underlying functionality works in both modes!