#!/usr/bin/env python3
"""Check for HTTP URLs in the scraped list that might redirect to HTTPS."""

import asyncio
from pathlib import Path

async def analyze_url_redirects(urls_file: Path):
    """Analyze URLs to identify HTTP redirects."""
    
    if not urls_file.exists():
        print(f"❌ File not found: {urls_file}")
        return
    
    # Read URLs from file
    with open(urls_file, 'r') as f:
        lines = f.readlines()
    
    urls = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#'):
            urls.append(line)
    
    print(f"📋 Analyzing {len(urls)} URLs for redirect potential...")
    
    # Categorize URLs
    http_urls = []
    https_urls = []
    other_urls = []
    
    for url in urls:
        if url.startswith('http://'):
            http_urls.append(url)
        elif url.startswith('https://'):
            https_urls.append(url)
        else:
            other_urls.append(url)
    
    print(f"\n📊 URL Analysis:")
    print(f"   🔒 HTTPS URLs: {len(https_urls)}")
    print(f"   🔓 HTTP URLs: {len(http_urls)} (may redirect)")
    print(f"   ❓ Other URLs: {len(other_urls)}")
    
    if http_urls:
        print(f"\n🔀 HTTP URLs that likely redirect to HTTPS:")
        print(f"   (These will be automatically handled by the screenshot tool)")
        for i, url in enumerate(http_urls[:10], 1):  # Show first 10
            print(f"   {i}. {url}")
        
        if len(http_urls) > 10:
            print(f"   ... and {len(http_urls) - 10} more HTTP URLs")
        
        print(f"\n💡 Test redirect handling:")
        print(f"   uv run site-analyser screenshot \\")
        print(f"     --urls {http_urls[0] if http_urls else 'http://example.com'} \\")
        print(f"     --output-dir ./redirect-test \\")
        print(f"     --verbose")
    
    if other_urls:
        print(f"\n❓ URLs with unusual schemes:")
        for url in other_urls[:5]:
            print(f"   • {url}")
    
    # Check for common redirect patterns
    redirect_candidates = []
    for url in urls:
        # Look for sites that commonly redirect from HTTP to HTTPS
        if any(pattern in url.lower() for pattern in [
            'www.', '.com', '.co.uk', '.org', '.net', 'tax', 'mtd', 'vat'
        ]) and url.startswith('http://'):
            redirect_candidates.append(url)
    
    print(f"\n🎯 High-probability redirect candidates: {len(redirect_candidates)}")
    
    return {
        'total_urls': len(urls),
        'http_urls': len(http_urls),
        'https_urls': len(https_urls),
        'other_urls': len(other_urls),
        'redirect_candidates': len(redirect_candidates)
    }

async def main():
    """Main function to check redirect potential in URL files."""
    print("🔍 URL Redirect Analysis Tool")
    print("=" * 40)
    
    # Check common URL files
    url_files = [
        Path("./minimal-urls.txt"),
        Path("./hmrc-software-urls.txt"),
        Path("./test-urls.txt")
    ]
    
    found_files = []
    for file_path in url_files:
        if file_path.exists():
            found_files.append(file_path)
    
    if not found_files:
        print("❌ No URL files found. Looking for:")
        for file_path in url_files:
            print(f"   • {file_path}")
        return
    
    print(f"📁 Found URL files:")
    for file_path in found_files:
        print(f"   • {file_path}")
    
    print()
    
    # Analyze each file
    total_stats = {
        'total_urls': 0,
        'http_urls': 0,
        'https_urls': 0,
        'redirect_candidates': 0
    }
    
    for file_path in found_files:
        print(f"\n📄 Analyzing {file_path}:")
        print("-" * 30)
        
        stats = await analyze_url_redirects(file_path)
        if stats:
            for key in total_stats:
                total_stats[key] += stats[key]
    
    if len(found_files) > 1:
        print(f"\n📈 Combined Statistics:")
        print(f"   Total URLs: {total_stats['total_urls']}")
        print(f"   HTTP URLs: {total_stats['http_urls']}")
        print(f"   HTTPS URLs: {total_stats['https_urls']}")
        print(f"   Redirect candidates: {total_stats['redirect_candidates']}")
    
    print(f"\n✅ Redirect analysis complete!")
    print(f"💡 The screenshot tool automatically handles HTTP → HTTPS redirects")

if __name__ == "__main__":
    asyncio.run(main())