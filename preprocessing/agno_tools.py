"""
Agno agent tool wrappers for the preprocessing module.

This module provides @tool decorated versions of the preprocessing functions
optimized for Agno agent usage with sensible defaults for AI workflows.
"""

from typing import List, Dict, Any, Union

# Optional import - only works if agno is installed
try:
    from agno.tools import tool
    AGNO_AVAILABLE = True
except ImportError:
    # Create a no-op decorator if agno isn't installed
    def tool(func):
        """No-op decorator when agno is not available."""
        func._is_agno_tool = False
        return func
    AGNO_AVAILABLE = False

from .tools import scrape_websites as _scrape_websites
from .tools import check_ssl_certificates as _check_ssl_certificates
from .tools import load_urls_from_file as _load_urls_from_file


@tool
async def scrape_websites(
    urls: Union[List[str], str],
    job_id: str = None,
    output_dir: str = "./scraping_output",
    timeout_ms: int = 30000,
    max_concurrent: int = 5,
    return_html: bool = False  # Default to False for agents to reduce token usage
) -> Dict[str, Any]:
    """
    Scrape websites and capture screenshots, HTML content, and SSL information.
    
    Optimized for Agno agent usage with conservative defaults to manage token usage.
    Screenshots and metadata are always captured, but HTML content is optional.
    
    Args:
        urls: Single URL or list of URLs to scrape
        job_id: Optional job identifier for tracking (auto-generated if not provided)
        output_dir: Directory to save screenshots and results
        timeout_ms: Page load timeout in milliseconds (default: 30000)
        max_concurrent: Maximum concurrent scraping tasks (default: 5)
        return_html: Whether to include full HTML in results (default: False to save tokens)
        
    Returns:
        Dictionary containing:
        - success: Boolean indicating if operation completed
        - job_id: String identifier for this scraping job
        - summary: Dict with counts of successful/failed scrapes
        - results: List of scraping results for each URL with company names, SSL info, performance data
        - output_paths: Dict with paths to generated screenshot and result files
        
    Example:
        >>> result = await scrape_websites(["https://example.com", "https://competitor.com"])
        >>> if result['success']:
        >>>     for site in result['results']:
        >>>         print(f"Company: {site['content']['company_name']}")
        >>>         print(f"SSL Valid: {site['ssl']['is_valid']}")
        >>>         print(f"Load Time: {site['performance']['load_time_ms']}ms")
    """
    return await _scrape_websites(
        urls=urls,
        job_id=job_id,
        output_dir=output_dir,
        timeout_ms=timeout_ms,
        max_concurrent=max_concurrent,
        return_html=return_html,
        save_screenshots=True  # Always save screenshots for agents
    )


@tool
async def check_ssl_certificates(urls: Union[List[str], str]) -> Dict[str, Any]:
    """
    Check SSL certificate information for websites without full scraping.
    
    Lightweight function that only analyzes SSL certificates, perfect for
    security audits or certificate monitoring workflows.
    
    Args:
        urls: Single URL or list of URLs to check SSL certificates for
        
    Returns:
        Dictionary containing:
        - success: Boolean indicating if operation completed
        - summary: Dict with SSL statistics (total, valid, expiring soon)
        - results: List with SSL details for each URL including validity, 
          expiry dates, certificate authorities, and error messages
          
    Example:
        >>> result = await check_ssl_certificates(["https://example.com", "https://expired.badssl.com"])
        >>> print(f"Valid SSL certificates: {result['summary']['valid_ssl']}")
        >>> for site in result['results']:
        >>>     ssl_info = site['ssl']
        >>>     if ssl_info['days_until_expiry'] and ssl_info['days_until_expiry'] < 30:
        >>>         print(f"⚠️ {site['url']} certificate expires in {ssl_info['days_until_expiry']} days!")
    """
    return await _check_ssl_certificates(urls)


@tool 
def load_urls_from_file(file_path: str) -> Dict[str, Any]:
    """
    Load URLs from a text file for batch processing operations.
    
    Reads URLs from a text file (one per line) and returns them in a structured format.
    Lines starting with # are treated as comments and ignored.
    
    Args:
        file_path: Path to text file containing URLs (one per line)
        
    Returns:
        Dictionary containing:
        - success: Boolean indicating if file was loaded successfully
        - urls: List of URLs found in the file
        - count: Number of URLs loaded
        - source_file: Absolute path to the source file
        
    Example:
        >>> result = load_urls_from_file("competitor-sites.txt")
        >>> if result['success']:
        >>>     urls = result['urls']
        >>>     print(f"Loaded {len(urls)} URLs for analysis")
        >>>     # Use URLs with other tools
        >>>     scrape_result = await scrape_websites(urls)
    """
    return _load_urls_from_file(file_path)


@tool
async def quick_site_analysis(
    urls: Union[List[str], str],
    job_id: str = None,
    focus: str = "security"  # "security", "performance", "content"
) -> Dict[str, Any]:
    """
    Perform focused analysis of websites based on specified criteria.
    
    This is a high-level analysis tool that combines scraping and SSL checking
    with intelligent filtering based on the analysis focus area.
    
    Args:
        urls: Single URL or list of URLs to analyze
        job_id: Optional job identifier for tracking
        focus: Analysis focus area - "security", "performance", or "content"
        
    Returns:
        Dictionary with analysis results optimized for the specified focus area
        
    Example:
        >>> result = await quick_site_analysis(["https://example.com"], focus="security")
        >>> print(result['insights']['security_summary'])
    """
    # First check SSL for all sites (lightweight)
    ssl_results = await _check_ssl_certificates(urls)
    
    if not ssl_results['success']:
        return {
            'success': False,
            'error': f"SSL check failed: {ssl_results.get('error', 'Unknown error')}",
            'insights': {}
        }
    
    # Filter URLs based on focus
    if focus == "security":
        # For security focus, prioritize sites with HTTPS
        target_urls = [
            r['url'] for r in ssl_results['results'] 
            if r['ssl']['has_ssl']
        ]
        timeout = 20000  # Shorter timeout for security checks
    elif focus == "performance":
        # For performance, check all sites
        target_urls = [r['url'] for r in ssl_results['results']]
        timeout = 45000  # Longer timeout to measure slow sites
    else:  # content focus
        # For content, prioritize working sites
        target_urls = [
            r['url'] for r in ssl_results['results'] 
            if not r['ssl'].get('certificate_error')
        ]
        timeout = 30000  # Standard timeout
    
    if not target_urls:
        return {
            'success': True,
            'insights': {
                'focus': focus,
                'sites_analyzed': 0,
                'reason': 'No suitable sites found for analysis focus'
            }
        }
    
    # Perform full scraping
    scrape_results = await _scrape_websites(
        urls=target_urls,
        job_id=job_id,
        timeout_ms=timeout,
        return_html=(focus == "content"),  # Only return HTML for content analysis
        save_screenshots=True
    )
    
    if not scrape_results['success']:
        return {
            'success': False,
            'error': f"Scraping failed: {scrape_results.get('error', 'Unknown error')}",
            'insights': {}
        }
    
    # Generate focused insights
    insights = _generate_focused_insights(
        ssl_results['results'], 
        scrape_results['results'], 
        focus
    )
    
    return {
        'success': True,
        'job_id': scrape_results.get('job_id'),
        'focus': focus,
        'insights': insights,
        'raw_data': {
            'ssl_summary': ssl_results['summary'],
            'scraping_summary': scrape_results['summary'],
            'output_paths': scrape_results.get('output_paths', {})
        }
    }


def _generate_focused_insights(ssl_results: List[Dict], scrape_results: List[Dict], focus: str) -> Dict[str, Any]:
    """Generate insights based on analysis focus."""
    insights = {'focus': focus, 'sites_analyzed': len(scrape_results)}
    
    if focus == "security":
        ssl_issues = []
        for ssl_result in ssl_results:
            ssl_info = ssl_result['ssl']
            if not ssl_info['is_valid']:
                ssl_issues.append({
                    'url': ssl_result['url'],
                    'issue': ssl_info.get('certificate_error', 'Invalid certificate')
                })
            elif ssl_info.get('days_until_expiry', 999) < 30:
                ssl_issues.append({
                    'url': ssl_result['url'],
                    'issue': f"Certificate expires in {ssl_info['days_until_expiry']} days"
                })
        
        insights['security_summary'] = {
            'ssl_issues_found': len(ssl_issues),
            'ssl_issues': ssl_issues,
            'https_adoption': sum(1 for r in ssl_results if r['ssl']['has_ssl']),
            'total_sites': len(ssl_results)
        }
    
    elif focus == "performance":
        performance_data = []
        for result in scrape_results:
            if result['status']['status'] == 'success':
                load_time = result['performance']['load_time_ms']
                performance_data.append({
                    'url': result['url']['final'],
                    'company': result['content']['company_name'],
                    'load_time_ms': load_time,
                    'performance_grade': 'fast' if load_time < 2000 else 'slow' if load_time > 5000 else 'medium'
                })
        
        insights['performance_summary'] = {
            'average_load_time': sum(p['load_time_ms'] for p in performance_data) / len(performance_data) if performance_data else 0,
            'fast_sites': sum(1 for p in performance_data if p['performance_grade'] == 'fast'),
            'slow_sites': sum(1 for p in performance_data if p['performance_grade'] == 'slow'),
            'site_performance': performance_data
        }
    
    else:  # content focus
        content_data = []
        for result in scrape_results:
            if result['status']['status'] == 'success':
                content_data.append({
                    'url': result['url']['final'],
                    'company': result['content']['company_name'],
                    'html_size': result['content']['html_size'],
                    'has_html_file': bool(result['content'].get('html_path')),
                    'has_screenshot': bool(result['content'].get('screenshot_path'))
                })
        
        insights['content_summary'] = {
            'sites_with_content': len(content_data),
            'average_html_size': sum(c['html_size'] for c in content_data) / len(content_data) if content_data else 0,
            'companies_found': [c['company'] for c in content_data],
            'content_details': content_data
        }
    
    return insights


# Export decorated tools for easy import
AGNO_TOOLS = [
    scrape_websites,
    check_ssl_certificates, 
    load_urls_from_file,
    quick_site_analysis
]

# Metadata for tool discovery
TOOL_METADATA = {
    "scrape_websites": {
        "description": "Comprehensive website scraping with screenshots and SSL analysis",
        "category": "data_collection",
        "complexity": "high",
        "estimated_time": "2-10 seconds per URL"
    },
    "check_ssl_certificates": {
        "description": "Lightweight SSL certificate validation and expiry checking", 
        "category": "security",
        "complexity": "low",
        "estimated_time": "1-2 seconds per URL"
    },
    "load_urls_from_file": {
        "description": "Load URLs from text files for batch processing",
        "category": "utility",
        "complexity": "low", 
        "estimated_time": "<1 second"
    },
    "quick_site_analysis": {
        "description": "Intelligent site analysis with configurable focus areas",
        "category": "analysis",
        "complexity": "high",
        "estimated_time": "5-15 seconds per URL"
    }
}