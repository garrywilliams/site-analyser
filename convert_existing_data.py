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
    # Extract domain from filename
    filename_parts = filename.split('_')
    if len(filename_parts) >= 3:
        # Get domain part (usually index 1)
        domain_part = filename_parts[1]
        
        # Try to match with URLs in list
        for url in urls_list:
            # Convert URL to expected domain format
            url_domain = url.replace('https://', '').replace('http://', '').replace('www.', '').replace('/', '').replace(':', '_').replace('.', '_')
            if domain_part == url_domain or domain_part in url_domain:
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
    files_by_url = {}
    
    # Find all files with the job ID
    for file_path in directory.iterdir():
        if not file_path.is_file():
            continue
            
        filename = file_path.name
        file_job_id = extract_job_id_from_filename(filename)
        
        if file_job_id == job_id:
            # Determine file type
            if filename.endswith('_screenshot.png'):
                url_key = filename.replace(f'{job_id}_', '').replace('_screenshot.png', '')
                if url_key not in files_by_url:
                    files_by_url[url_key] = {}
                files_by_url[url_key]['screenshot_file'] = filename
                files_by_url[url_key]['screenshot_path'] = file_path
                
            elif filename.endswith('_html.html'):
                url_key = filename.replace(f'{job_id}_', '').replace('_html.html', '')
                if url_key not in files_by_url:
                    files_by_url[url_key] = {}
                files_by_url[url_key]['html_file'] = filename
                files_by_url[url_key]['html_path'] = file_path
    
    return files_by_url

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
    
    # Find files in directory
    files_by_key = find_matching_files(directory, job_id)
    if not files_by_key:
        raise ValueError(f"No files found with job ID {job_id} in {directory}")
    
    print(f"Found {len(files_by_key)} file groups for job ID {job_id}")
    print(f"Loaded {len(urls)} URLs from {urls_file}")
    
    # Create results structure
    results = []
    matched_urls = set()
    
    for url_key, files in files_by_key.items():
        # Try to match to original URL
        matched_url = None
        for url in urls:
            url_normalized = url.replace('https://', '').replace('http://', '').replace('www.', '').replace('/', '').replace(':', '_').replace('.', '_')
            if url_key.startswith(url_normalized) or url_normalized.startswith(url_key):
                matched_url = url
                matched_urls.add(url)
                break
        
        if not matched_url:
            # Try partial matching
            domain_from_key = url_key.split('_')[0] if '_' in url_key else url_key
            for url in urls:
                if domain_from_key in url.replace('www.', ''):
                    matched_url = url
                    matched_urls.add(url)
                    break
        
        if not matched_url:
            print(f"Warning: Could not match file key '{url_key}' to any URL")
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