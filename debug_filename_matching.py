#!/usr/bin/env python3
"""Debug filename to URL matching for conversion script."""

import hashlib
from pathlib import Path
from typing import List

def analyze_filename_pattern(filename: str) -> dict:
    """Analyze a filename to understand its structure."""
    parts = filename.split('_')
    
    analysis = {
        'filename': filename,
        'parts': parts,
        'part_count': len(parts),
        'suspected_job_id': parts[0] if parts else None,
        'suspected_domain': parts[1:-2] if len(parts) >= 4 else [],
        'suspected_hash': parts[-2] if len(parts) >= 2 else None,
        'suspected_type': parts[-1].split('.')[0] if parts else None,
        'extension': filename.split('.')[-1] if '.' in filename else None
    }
    
    return analysis

def test_url_matching(url: str, filename: str) -> dict:
    """Test if URL matches filename pattern."""
    # Calculate actual hash
    actual_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    
    # Analyze filename
    analysis = analyze_filename_pattern(filename)
    
    # Check domain conversion
    url_clean = url.replace('https://', '').replace('http://', '').split('/')[0]
    expected_domain = url_clean.replace('.', '_').replace(':', '_')
    
    filename_domain = '_'.join(analysis['suspected_domain']) if analysis['suspected_domain'] else ''
    
    match_result = {
        'url': url,
        'filename': filename,
        'actual_hash': actual_hash,
        'filename_hash': analysis['suspected_hash'],
        'hash_match': actual_hash == analysis['suspected_hash'],
        'expected_domain': expected_domain,
        'filename_domain': filename_domain,
        'domain_match': expected_domain == filename_domain,
        'analysis': analysis
    }
    
    return match_result

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Debug filename to URL matching')
    parser.add_argument('--directory', type=Path, required=True,
                        help='Directory containing files to analyze')
    parser.add_argument('--urls-file', type=Path, required=True,
                        help='File containing URLs')
    parser.add_argument('--sample-count', type=int, default=5,
                        help='Number of files to analyze')
    
    args = parser.parse_args()
    
    # Load URLs
    urls = []
    if args.urls_file.exists():
        with open(args.urls_file, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    # Get sample files
    files = list(args.directory.glob('*.png'))[:args.sample_count]
    if not files:
        files = list(args.directory.glob('*.html'))[:args.sample_count]
    
    print(f"🔍 Analyzing {len(files)} files from {args.directory}")
    print(f"📋 Loaded {len(urls)} URLs from {args.urls_file}")
    print("=" * 80)
    
    for file_path in files:
        filename = file_path.name
        analysis = analyze_filename_pattern(filename)
        
        print(f"\n📄 File: {filename}")
        print(f"   Parts: {analysis['parts']}")
        print(f"   Job ID: {analysis['suspected_job_id']}")
        print(f"   Domain parts: {analysis['suspected_domain']}")
        print(f"   Hash: {analysis['suspected_hash']}")
        print(f"   Type: {analysis['suspected_type']}")
        
        # Try to match with URLs
        best_match = None
        for url in urls[:10]:  # Test first 10 URLs
            match = test_url_matching(url, filename)
            if match['hash_match']:
                best_match = match
                print(f"   ✅ HASH MATCH: {url}")
                break
            elif match['domain_match']:
                if not best_match:
                    best_match = match
                print(f"   🔶 Domain match: {url}")
        
        if not best_match and urls:
            # Show what we would expect for first URL
            test_match = test_url_matching(urls[0], filename)
            print(f"   ❌ No matches found")
            print(f"   💡 For '{urls[0]}' we'd expect:")
            print(f"      Domain: {test_match['expected_domain']}")  
            print(f"      Hash: {test_match['actual_hash']}")
    
    print("\n" + "=" * 80)
    print("🎯 Matching Strategy:")
    print("1. Hash matching: Calculate MD5(url)[:8] and compare with filename hash")
    print("2. Domain matching: Convert URL domain to filename format (dots->underscores)")
    print("3. Pattern: {job_id}_{domain_parts}_{hash}_{type}.{ext}")

if __name__ == "__main__":
    main()