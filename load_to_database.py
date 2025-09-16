#!/usr/bin/env python3
"""Load screenshot and HTML data into PostgreSQL database for analysis."""

import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import asyncpg
import structlog
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = structlog.get_logger()

class DatabaseLoader:
    """Loads scraped site data into PostgreSQL database."""
    
    def __init__(self):
        self.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'site_analysis'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
        }
        
    async def create_connection(self) -> asyncpg.Connection:
        """Create database connection."""
        try:
            conn = await asyncpg.connect(**self.db_config)
            logger.info("database_connected", host=self.db_config['host'], database=self.db_config['database'])
            return conn
        except Exception as e:
            logger.error("database_connection_failed", error=str(e), config=self.db_config)
            raise
    
    def calculate_image_hash(self, image_path: Path) -> str:
        """Calculate SHA-256 hash of image file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(image_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error("image_hash_failed", path=str(image_path), error=str(e))
            raise
    
    def extract_company_info(self, html_content: str, url: str) -> Dict[str, Optional[str]]:
        """Extract company name and summary from HTML content."""
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try to extract company name from various sources
            company_name = None
            
            # 1. Try meta property="og:site_name"
            og_site_name = soup.find('meta', property='og:site_name')
            if og_site_name:
                company_name = og_site_name.get('content', '').strip()
            
            # 2. Try title tag (clean and remove common suffixes)
            if not company_name:
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()
                    # Remove common suffixes and clean
                    suffixes_to_remove = [
                        ' - Home', ' | Home', ' - Official Site', ' | Official Site',
                        ' - Homepage', ' | Homepage', ' - Welcome', ' | Welcome',
                        ' Ltd', ' Limited', ' Inc', ' Corporation', ' Corp',
                        ' - Making Tax Digital', ' - MTD', ' - VAT', ' - Software',
                        ' - Accounting', ' - Bookkeeping', ' - Tax'
                    ]
                    for suffix in suffixes_to_remove:
                        title = title.replace(suffix, '')
                    
                    # Remove common prefixes
                    prefixes_to_remove = ['Welcome to ', 'Home - ', 'Homepage - ']
                    for prefix in prefixes_to_remove:
                        if title.startswith(prefix):
                            title = title[len(prefix):]
                    
                    # Clean and validate
                    title = title.strip()
                    if len(title) > 3 and len(title) <= 100:  # Reasonable length
                        company_name = title
            
            # 3. Try h1 tag as fallback (clean it too)
            if not company_name:
                h1_tag = soup.find('h1')
                if h1_tag:
                    h1_text = h1_tag.get_text().strip()
                    # Clean h1 text similar to title
                    if len(h1_text) > 3 and len(h1_text) <= 80 and not any(
                        phrase in h1_text.lower() for phrase in [
                            'welcome', 'homepage', 'home page', 'making tax digital',
                            'vat software', 'accounting software'
                        ]
                    ):
                        company_name = h1_text
            
            # 4. Try to find company name in common locations
            if not company_name:
                # Look for copyright notices
                for element in soup.find_all(text=True):
                    text = element.strip()
                    if '©' in text or 'copyright' in text.lower():
                        # Extract company name from copyright
                        import re
                        copyright_match = re.search(r'©\s*\d{4}[-\d]*\s*([^.]+)', text)
                        if copyright_match:
                            potential_name = copyright_match.group(1).strip()
                            if len(potential_name) > 3 and len(potential_name) <= 50:
                                company_name = potential_name
                                break
            
            # 5. Use domain as ultimate fallback (make it prettier)
            if not company_name:
                domain = urlparse(url).netloc.replace('www.', '')
                # Convert domain to a more readable format
                domain_parts = domain.split('.')
                if len(domain_parts) >= 2:
                    # Use the main part of domain, capitalize first letter
                    main_part = domain_parts[0]
                    company_name = main_part.capitalize()
                else:
                    company_name = domain
            
            # Extract description/summary
            summary = None
            
            # 1. Try meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', property='og:description')
            if meta_desc:
                summary = meta_desc.get('content', '').strip()
            
            # 2. Try first meaningful paragraph as fallback
            if not summary:
                paragraphs = soup.find_all('p')
                for p in paragraphs[:5]:  # Check first few paragraphs
                    text = p.get_text().strip()
                    # Skip very short paragraphs or navigation text
                    if (len(text) > 50 and 
                        not any(skip_word in text.lower() for skip_word in [
                            'cookie', 'navigation', 'menu', 'skip to', 'accessibility'
                        ])):
                        summary = text[:500]  # Limit length
                        break
            
            return {
                'company_name': company_name,
                'summary': summary
            }
            
        except Exception as e:
            logger.warning("company_info_extraction_failed", url=url, error=str(e))
            # Fallback to domain
            domain = urlparse(url).netloc.replace('www.', '')
            domain_parts = domain.split('.')
            if len(domain_parts) >= 2:
                fallback_name = domain_parts[0].capitalize()
            else:
                fallback_name = domain
            return {
                'company_name': fallback_name,
                'summary': None
            }
    
    def load_company_mapping(self, mapping_file: Path) -> Dict[str, str]:
        """Load company name mapping from original scraper data if available."""
        company_map = {}
        
        if not mapping_file.exists():
            logger.info("no_company_mapping_file", path=str(mapping_file))
            return company_map
        
        try:
            # Handle both JSON and text formats
            if mapping_file.suffix == '.json':
                with open(mapping_file, 'r') as f:
                    data = json.load(f)
                
                # Extract from JSON entries format
                entries = data.get('entries', [])
                for entry in entries:
                    company_name = entry.get('company_name')
                    website_url = entry.get('website_url')
                    if company_name and website_url:
                        # Clean the company name from HMRC scraper
                        cleaned_name = self._clean_hmrc_company_name(company_name)
                        if cleaned_name:
                            company_map[website_url] = cleaned_name
                        
            else:
                # Handle text format
                with open(mapping_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Handle different formats:
                            if ' - ' in line and line.startswith('# Company:'):
                                # Format: "# Company: Company Name"
                                continue  # Skip, we'll use the URL line
                            elif line.startswith('http'):
                                # This is a URL line, but we need the company from previous lines
                                continue  # For now, just store URLs we see
                            elif ' - ' in line:
                                # Format: "Company Name - https://example.com"
                                parts = line.split(' - ', 1)
                                if len(parts) == 2:
                                    company_name = parts[0].strip()
                                    url = parts[1].strip()
                                    company_map[url] = company_name
                                    
            logger.info("company_mapping_loaded", count=len(company_map), format=mapping_file.suffix)
            
        except Exception as e:
            logger.warning("company_mapping_load_failed", path=str(mapping_file), error=str(e))
        
        return company_map
    
    def _clean_hmrc_company_name(self, raw_name: str) -> Optional[str]:
        """Clean company name extracted from HMRC scraper data."""
        if not raw_name:
            return None
        
        # The HMRC scraper sometimes captures the entire description block
        # We need to extract just the company/product name
        
        # Look for patterns like "! Company Name! Rest of description..."
        import re
        
        # Pattern 1: Handle names with symbols like "! Company Name! rest..."
        # First, try to extract the name from patterns like "! Name! Name is suitable..."
        duplicate_pattern = re.match(r'^[!#\*\+\-]*\s*(.+?)[!#\*\+\-]*\s*\1\s*(is suitable|software type)', raw_name, re.IGNORECASE)
        if duplicate_pattern:
            potential_name = duplicate_pattern.group(1).strip()
            # Remove any remaining symbols
            potential_name = re.sub(r'^[!#\*\+\-\s]+|[!#\*\+\-\s]+$', '', potential_name)
            if len(potential_name) > 2 and len(potential_name) <= 50:
                return potential_name
        
        # Pattern 2: Simple symbol extraction - "! Company Name" or "# Company Name"
        symbol_pattern = re.match(r'^[!#\*\+\-]*\s*([A-Za-z][^!#\*\+\-]*?)(?:[!#\*\+\-]+|$)', raw_name)
        if symbol_pattern:
            potential_name = symbol_pattern.group(1).strip()
            # Check if it looks like a reasonable company name
            if (len(potential_name) > 2 and len(potential_name) <= 50 and
                not any(phrase in potential_name.lower() for phrase in [
                    'is suitable', 'software type', 'vat specific'
                ])):
                return potential_name
        
        # Pattern 2: Extract first meaningful part before common separators
        separators = [
            ' is suitable for', ' software type:', 'Software type:', 
            'VAT specific features:', ' - ', ' | '
        ]
        
        for separator in separators:
            if separator in raw_name:
                before_separator = raw_name.split(separator)[0].strip()
                # Clean up symbols
                before_separator = re.sub(r'^[!#\*\+\-\s]+', '', before_separator)
                before_separator = re.sub(r'[!#\*\+\-\s]+$', '', before_separator)
                
                if len(before_separator) > 2 and len(before_separator) <= 80:
                    return before_separator
        
        # Pattern 3: Try to find the actual company name in the first part
        words = raw_name.split()
        if words:
            # Look for words that might be company names (capitalized, not common words)
            company_words = []
            common_words = {'is', 'suitable', 'for', 'businesses', 'or', 'agents', 'software', 'type', 'vat'}
            
            for word in words[:10]:  # Only check first 10 words
                clean_word = re.sub(r'[!#\*\+\-]', '', word).strip()
                if (clean_word and 
                    len(clean_word) > 1 and 
                    clean_word.lower() not in common_words and
                    not clean_word.lower().startswith('bridg')):  # Avoid "bridging"
                    company_words.append(clean_word)
                    if len(' '.join(company_words)) > 40:  # Don't make it too long
                        break
                elif company_words:  # If we hit a common word after finding company words, stop
                    break
            
            if company_words:
                company_name = ' '.join(company_words)
                if len(company_name) > 2:
                    return company_name
        
        # If all else fails, return None to use HTML extraction
        return None
    
    async def load_screenshot_results(self, results_file: Path, company_mapping: Dict[str, str] = None) -> List[Dict]:
        """Load and process screenshot results JSON file."""
        if company_mapping is None:
            company_mapping = {}
            
        try:
            with open(results_file, 'r') as f:
                data = json.load(f)
            
            results_dir = results_file.parent
            job_id = data.get('job_id')
            viewport = data.get('viewport', 'unknown')
            
            records = []
            
            for result in data.get('results', []):
                try:
                    original_url = result['original_url']
                    final_url = result.get('final_url', original_url)
                    screenshot_file = result.get('screenshot_file')
                    html_file = result.get('html_file')
                    
                    if not screenshot_file:
                        logger.warning("no_screenshot_file", url=original_url, job_id=job_id)
                        continue
                    
                    # Build file paths
                    screenshot_path = results_dir / screenshot_file
                    html_path = results_dir / html_file if html_file else None
                    
                    # Check if files exist
                    if not screenshot_path.exists():
                        logger.error("screenshot_file_missing", path=str(screenshot_path), url=original_url)
                        continue
                    
                    # Read image data and calculate hash
                    with open(screenshot_path, 'rb') as f:
                        image_data = f.read()
                    image_hash = hashlib.sha256(image_data).hexdigest()
                    
                    # Read HTML content if available
                    html_content = None
                    html_content_length = 0
                    if html_path and html_path.exists():
                        with open(html_path, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                        html_content_length = len(html_content)
                    
                    # Extract company information with intelligent prioritization
                    company_info = {'company_name': None, 'summary': None}
                    
                    # 1. Try to get from company mapping (original scraper data)
                    mapped_company = company_mapping.get(original_url) or company_mapping.get(final_url)
                    
                    # 2. Extract from HTML if available
                    html_extracted_info = None
                    if html_content:
                        html_extracted_info = self.extract_company_info(html_content, original_url)
                        company_info['summary'] = html_extracted_info['summary']
                    
                    # 3. Prioritize the best company name source
                    # Prefer HTML extraction if HMRC data looks poor (too long, generic, etc.)
                    if mapped_company and html_extracted_info:
                        # If HMRC name is very long or contains generic terms, prefer HTML
                        if (len(mapped_company) > 50 or 
                            any(term in mapped_company.lower() for term in [
                                'is suitable for', 'software type', 'vat specific', 
                                'bridging software', 'record-keeping'
                            ])):
                            # HTML extraction is likely better
                            company_info['company_name'] = html_extracted_info['company_name']
                            logger.info("preferred_html_over_mapping", 
                                      url=original_url,
                                      hmrc_name=mapped_company[:100],
                                      html_name=html_extracted_info['company_name'])
                        else:
                            # HMRC name looks clean, use it
                            company_info['company_name'] = mapped_company
                    elif mapped_company:
                        # Only HMRC name available
                        company_info['company_name'] = mapped_company
                    elif html_extracted_info:
                        # Only HTML extraction available
                        company_info['company_name'] = html_extracted_info['company_name']
                    else:
                        # Fallback to domain
                        domain_parts = urlparse(original_url).netloc.replace('www.', '').split('.')
                        if len(domain_parts) >= 2:
                            company_info['company_name'] = domain_parts[0].capitalize()
                        else:
                            company_info['company_name'] = urlparse(original_url).netloc.replace('www.', '')
                    
                    # Build database record
                    record = {
                        'job_id': job_id,
                        'original_url': original_url,
                        'final_url': final_url if final_url != original_url else None,
                        'company_name': company_info['company_name'],
                        'domain': urlparse(original_url).netloc,
                        'html_content': html_content,
                        'html_content_length': html_content_length,
                        'screenshot_image': image_data,
                        'screenshot_hash': image_hash,
                        'load_time_ms': result.get('load_time_ms'),
                        'redirected': result.get('redirected', False),
                        'viewport_size': viewport,
                        'screenshot_file_size': len(image_data),
                        'screenshot_filename': screenshot_file,
                        'html_filename': html_file,
                        'analysis_status': 'pending'
                    }
                    
                    records.append(record)
                    logger.info("record_prepared", url=original_url, company=company_info['company_name'], 
                              image_size=len(image_data), html_size=html_content_length)
                    
                except Exception as e:
                    logger.error("record_processing_failed", url=result.get('original_url', 'unknown'), 
                               error=str(e), job_id=job_id)
                    continue
            
            logger.info("screenshot_results_processed", file=str(results_file), total_records=len(records))
            return records
            
        except Exception as e:
            logger.error("screenshot_results_load_failed", file=str(results_file), error=str(e))
            raise
    
    async def insert_records(self, conn: asyncpg.Connection, records: List[Dict]):
        """Insert records into database."""
        if not records:
            logger.warning("no_records_to_insert")
            return
        
        insert_query = """
            INSERT INTO site_analysis_data (
                job_id, original_url, final_url, company_name, domain,
                html_content, html_content_length, screenshot_image, screenshot_hash,
                load_time_ms, redirected, viewport_size, screenshot_file_size,
                screenshot_filename, html_filename, analysis_status
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
            )
            ON CONFLICT (job_id, original_url) 
            DO UPDATE SET
                final_url = EXCLUDED.final_url,
                company_name = EXCLUDED.company_name,
                html_content = EXCLUDED.html_content,
                html_content_length = EXCLUDED.html_content_length,
                screenshot_image = EXCLUDED.screenshot_image,
                screenshot_hash = EXCLUDED.screenshot_hash,
                load_time_ms = EXCLUDED.load_time_ms,
                redirected = EXCLUDED.redirected,
                viewport_size = EXCLUDED.viewport_size,
                screenshot_file_size = EXCLUDED.screenshot_file_size,
                screenshot_filename = EXCLUDED.screenshot_filename,
                html_filename = EXCLUDED.html_filename,
                processed_at = NOW()
        """
        
        inserted = 0
        updated = 0
        
        async with conn.transaction():
            for record in records:
                try:
                    result = await conn.execute(insert_query, 
                        record['job_id'],
                        record['original_url'],
                        record['final_url'], 
                        record['company_name'],
                        record['domain'],
                        record['html_content'],
                        record['html_content_length'],
                        record['screenshot_image'],
                        record['screenshot_hash'],
                        record['load_time_ms'],
                        record['redirected'],
                        record['viewport_size'],
                        record['screenshot_file_size'],
                        record['screenshot_filename'],
                        record['html_filename'],
                        record['analysis_status']
                    )
                    
                    if 'INSERT' in result:
                        inserted += 1
                    else:
                        updated += 1
                        
                except Exception as e:
                    logger.error("record_insert_failed", url=record['original_url'], error=str(e))
                    raise
        
        logger.info("database_insert_completed", inserted=inserted, updated=updated, total=len(records))

async def main():
    """Main function to load screenshot results into database."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Load screenshot results into PostgreSQL database')
    parser.add_argument('--results-file', type=Path, required=True,
                        help='Path to screenshot_results.json file')
    parser.add_argument('--company-mapping', type=Path,
                        help='Optional path to company mapping file (format: "Company - URL")')
    parser.add_argument('--create-schema', action='store_true',
                        help='Create database schema before loading data')
    
    args = parser.parse_args()
    
    # Set up logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    if not args.results_file.exists():
        logger.error("results_file_not_found", path=str(args.results_file))
        sys.exit(1)
    
    loader = DatabaseLoader()
    
    try:
        conn = await loader.create_connection()
        
        # Create schema if requested
        if args.create_schema:
            schema_file = Path(__file__).parent / 'database' / 'schema.sql'
            if schema_file.exists():
                with open(schema_file, 'r') as f:
                    schema_sql = f.read()
                await conn.execute(schema_sql)
                logger.info("database_schema_created")
            else:
                logger.warning("schema_file_not_found", path=str(schema_file))
        
        # Load company mapping if provided
        company_mapping = {}
        if args.company_mapping:
            company_mapping = loader.load_company_mapping(args.company_mapping)
        
        # Process screenshot results
        records = await loader.load_screenshot_results(args.results_file, company_mapping)
        
        # Insert into database
        await loader.insert_records(conn, records)
        
        logger.info("database_load_completed", results_file=str(args.results_file))
        
    except Exception as e:
        logger.error("database_load_failed", error=str(e))
        sys.exit(1)
    finally:
        if 'conn' in locals():
            await conn.close()

if __name__ == "__main__":
    asyncio.run(main())