#!/usr/bin/env python3
"""Convert existing screenshot/HTML files to screenshot_results.json format for database loading."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import hashlib

def extract_job_id_from_filename(filename: str) -> Optional[str]:
    """Extract job ID from filename pattern: job_id_domain_hash_type.ext"""
    # Pattern: uuid_domain_hash_type.ext
    uuid_pattern = r'^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_'
    match = re.match(uuid_pattern, filename, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def extract_url_from_filename(filename: str, urls_list: List[str]) -> Optional[str]:
    """Try to match filename to original URL from list."""
    # Remove job ID prefix and file extension
    # Pattern: job_id_domain_parts_hash_type.ext
    parts = filename.split('_')
    
    if len(parts) < 4:  # Need at least job_id, domain_part, hash, type
        return None
    
    # Remove job ID (first part) and hash + type (last 2-3 parts)
    # The domain is everything in between
    domain_parts = parts[1:-2]  # Remove job_id, hash, and type
    
    # Try different domain reconstruction approaches
    possible_domains = []
    
    # Approach 1: Join all domain parts with dots
    if domain_parts:
        domain_with_dots = '.'.join(domain_parts)
        possible_domains.append(domain_with_dots)
        
        # Also try with www prefix
        if not domain_with_dots.startswith('www'):
            possible_domains.append(f"www.{domain_with_dots}")
    
    # Approach 2: Direct hash matching - calculate hash for each URL
    for url in urls_list:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        
        # Check if this hash matches the filename hash
        filename_hash = None
        if len(parts) >= 3:
            # Hash is typically the second-to-last part
            filename_hash = parts[-2]
            
        if filename_hash == url_hash:
            return url
    
    # Approach 3: Domain matching with URL list
    for url in urls_list:
        # Extract domain from URL
        url_clean = url.replace('https://', '').replace('http://', '').split('/')[0]
        url_domain_parts = url_clean.replace('.', '_').replace(':', '_')
        
        # Check if filename contains this domain pattern
        filename_domain = '_'.join(domain_parts)
        if (filename_domain == url_domain_parts or 
            filename_domain in url_domain_parts or
            url_domain_parts in filename_domain):
            return url
        
        # Also try without www
        url_no_www = url_clean.replace('www.', '')
        url_no_www_parts = url_no_www.replace('.', '_').replace(':', '_')
        if (filename_domain == url_no_www_parts or
            filename_domain in url_no_www_parts or
            url_no_www_parts in filename_domain):
            return url
    
    return None

def load_urls_from_file(urls_file: Path) -> List[str]:
    """Load URLs from text file."""
    urls = []
    if urls_file.exists():
        with open(urls_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
    return urls

def find_matching_files(directory: Path, job_id: str) -> Dict[str, Dict]:
    """Find all screenshot and HTML files for the job ID."""
    files_by_hash = {}
    
    # Find all files with the job ID
    for file_path in directory.iterdir():
        if not file_path.is_file():
            continue
            
        filename = file_path.name
        file_job_id = extract_job_id_from_filename(filename)
        
        if file_job_id == job_id:
            # Extract hash from filename for grouping
            # Pattern: job_id_domain_parts_hash_type.ext
            parts = filename.split('_')
            
            if len(parts) >= 3:
                # Determine file type and extract hash
                if filename.endswith('_screenshot.png'):
                    hash_key = parts[-2]  # Hash is second-to-last part
                    if hash_key not in files_by_hash:
                        files_by_hash[hash_key] = {}
                    files_by_hash[hash_key]['screenshot_file'] = filename
                    files_by_hash[hash_key]['screenshot_path'] = file_path
                    
                elif filename.endswith('_html.html'):
                    hash_key = parts[-2]  # Hash is second-to-last part  
                    if hash_key not in files_by_hash:
                        files_by_hash[hash_key] = {}
                    files_by_hash[hash_key]['html_file'] = filename
                    files_by_hash[hash_key]['html_path'] = file_path
    
    return files_by_hash

def create_screenshot_results_json(
    directory: Path, 
    urls_file: Path, 
    job_id: str,
    output_file: Path
) -> Dict:
    """Create screenshot_results.json from existing files."""
    
    # Load URLs from file
    urls = load_urls_from_file(urls_file)
    if not urls:
        raise ValueError(f"No URLs found in {urls_file}")
    
    # Find files in directory (now grouped by hash)
    files_by_hash = find_matching_files(directory, job_id)
    if not files_by_hash:
        raise ValueError(f"No files found with job ID {job_id} in {directory}")
    
    print(f"Found {len(files_by_hash)} file groups for job ID {job_id}")
    print(f"Loaded {len(urls)} URLs from {urls_file}")
    
    # Create results structure
    results = []
    matched_urls = set()
    
    for hash_key, files in files_by_hash.items():
        # Get a filename to work with for URL matching
        sample_filename = files.get('screenshot_file') or files.get('html_file')
        if not sample_filename:
            continue
            
        # Try to match filename to original URL using our improved logic
        matched_url = extract_url_from_filename(sample_filename, urls)
        
        if matched_url:
            matched_urls.add(matched_url)
        else:
            print(f"Warning: Could not match hash '{hash_key}' (file: {sample_filename}) to any URL")
            print(f"  Available URLs sample: {urls[:3]}...")
            continue
        
        # Get file info
        screenshot_file = files.get('screenshot_file')
        html_file = files.get('html_file')
        screenshot_path = files.get('screenshot_path')
        
        if not screenshot_file:
            print(f"Warning: No screenshot file found for {matched_url}")
            continue
        
        # Calculate load time estimate (from file modification time)
        load_time_ms = None
        if screenshot_path and screenshot_path.exists():
            # Use a default load time since we don't have the actual data
            load_time_ms = 1000  # 1 second default
        
        result = {
            "job_id": job_id,
            "original_url": matched_url,
            "final_url": matched_url,  # Assume no redirect since we don't have that data
            "redirected": False,
            "status": "success",
            "screenshot_file": screenshot_file,
            "html_file": html_file,
            "load_time_ms": load_time_ms,
            "error_message": None
        }
        
        results.append(result)
        print(f"Matched: {matched_url} -> {screenshot_file}")
    
    # Check for unmatched URLs
    unmatched_urls = set(urls) - matched_urls
    if unmatched_urls:
        print(f"\nWarning: {len(unmatched_urls)} URLs from file were not matched to files:")
        for url in sorted(unmatched_urls):
            print(f"  - {url}")
    
    # Create the complete results structure
    screenshot_results = {
        "job_id": job_id,
        "timestamp": datetime.now().isoformat(),
        "total_urls": len(results),
        "successful": len(results),
        "failed": 0,
        "redirected": 0,  # We don't have this information
        "save_html_enabled": bool(any(r.get('html_file') for r in results)),
        "urls": [r["original_url"] for r in results],
        "output_directory": str(directory),
        "viewport": "unknown",  # We don't have this information
        "timeout_seconds": 15,  # Default
        "results": results
    }
    
    # Write to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(screenshot_results, f, indent=2)
    
    print(f"\n✅ Created {output_file}")
    print(f"   📊 Matched {len(results)} URLs to files")
    print(f"   🖼️  Screenshots: {len([r for r in results if r.get('screenshot_file')])}")
    print(f"   📄 HTML files: {len([r for r in results if r.get('html_file')])}")
    
    return screenshot_results

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert existing screenshot/HTML files to database-loadable format')
    parser.add_argument('--directory', type=Path, required=True,
                        help='Directory containing screenshot and HTML files')
    parser.add_argument('--urls-file', type=Path, required=True,
                        help='Text file containing list of URLs (one per line)')
    parser.add_argument('--job-id', type=str, required=True,
                        help='Job ID to extract from filenames')
    parser.add_argument('--output', type=Path, default=None,
                        help='Output path for screenshot_results.json (default: directory/screenshot_results.json)')
    
    args = parser.parse_args()
    
    if not args.directory.exists():
        print(f"❌ Directory does not exist: {args.directory}")
        return 1
        
    if not args.urls_file.exists():
        print(f"❌ URLs file does not exist: {args.urls_file}")
        return 1
    
    if not args.output:
        args.output = args.directory / "screenshot_results.json"
    
    try:
        results = create_screenshot_results_json(
            directory=args.directory,
            urls_file=args.urls_file,
            job_id=args.job_id,
            output_file=args.output
        )
        
        print(f"\n🚀 Ready for database loading:")
        print(f"   python load_to_database.py --results-file {args.output} --create-schema")
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())