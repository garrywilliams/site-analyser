"""URL scraper for extracting vendor URLs from HMRC software list page."""

import re
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx
import structlog

logger = structlog.get_logger()


class HMRCSoftwareListScraper:
    """Scraper for HMRC Making Tax Digital software list page."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.base_url = "https://www.tax.service.gov.uk"
    
    async def scrape_software_urls(self, source_url: str) -> List[Dict[str, str]]:
        """
        Scrape software vendor URLs from HMRC software list page.
        
        Returns list of dicts with company_name, product_name, and website_url.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(source_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                software_entries = self._extract_software_entries(soup)
                
                logger.info(
                    "software_urls_scraped",
                    source_url=source_url,
                    total_entries=len(software_entries),
                    valid_urls=len([entry for entry in software_entries if entry.get('website_url')])
                )
                
                return software_entries
                
        except Exception as e:
            logger.error("software_scraping_failed", source_url=source_url, error=str(e))
            raise
    
    def _extract_software_entries(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract software entries from the parsed HTML."""
        entries = []
        
        # Look for the main content area first
        main_content = soup.find('main') or soup.find('div', class_='govuk-main-wrapper')
        
        if not main_content:
            logger.warning("could_not_find_main_content")
            return entries
        
        # Look for all list items - the software entries appear to be in lists
        list_items = main_content.find_all('li')
        
        if not list_items:
            # Fallback to looking for paragraphs if no list items found
            list_items = main_content.find_all('p')
        
        logger.debug(f"found_{len(list_items)}_potential_entries")
        
        for element in list_items:
            entry_text = element.get_text(strip=True)
            
            # Skip empty or very short entries (likely navigation or other elements)
            if not entry_text or len(entry_text) < 100:
                continue
            
            # Look for external links (not gov.uk internal links)
            links = element.find_all('a', href=True)
            website_url = None
            
            for link in links:
                href = link.get('href', '').strip()
                link_text = link.get_text(strip=True).lower()
                
                # Skip internal gov.uk links, anchors, and empty hrefs
                if (not href or 
                    href.startswith('#') or 
                    'gov.uk' in href or
                    href.startswith('mailto:') or
                    href.startswith('tel:')):
                    continue
                
                # This looks like an external website link
                if href.startswith('http'):
                    website_url = href
                    break
                elif '.' in href:  # Likely a domain without protocol
                    website_url = f"https://{href}"
                    break
            
            # Only process entries that have external website links
            if website_url:
                company_name, product_name = self._extract_names_from_text(entry_text)
                
                entry = {
                    'company_name': company_name or 'Unknown',
                    'product_name': product_name or 'Unknown', 
                    'website_url': website_url,
                    'entry_text': entry_text[:300] + '...' if len(entry_text) > 300 else entry_text
                }
                entries.append(entry)
                
                logger.debug(
                    "software_entry_found",
                    company=company_name,
                    product=product_name,
                    url=website_url,
                    text_preview=entry_text[:100] + "..."
                )
        
        # If still no entries found, try a more aggressive search
        if not entries:
            logger.warning("no_entries_found_trying_broader_search")
            entries = self._fallback_url_extraction(soup)
        
        return entries
    
    def _fallback_url_extraction(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Fallback method to extract URLs more aggressively."""
        entries = []
        
        # Find all external links in the entire document
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '').strip()
            
            # Filter for external URLs that look like business websites
            if (href.startswith('http') and 
                'gov.uk' not in href and
                'google.' not in href and
                'facebook.' not in href and
                'twitter.' not in href and
                'linkedin.' not in href and
                len(href) > 10):
                
                # Get surrounding context
                parent = link.parent
                context_text = ""
                if parent:
                    context_text = parent.get_text(strip=True)
                
                # Only include if there's substantial context (likely a software entry)
                if len(context_text) > 50:
                    company_name, product_name = self._extract_names_from_text(context_text)
                    
                    entry = {
                        'company_name': company_name or 'Unknown',
                        'product_name': product_name or 'Unknown',
                        'website_url': href,
                        'entry_text': context_text[:200] + '...' if len(context_text) > 200 else context_text
                    }
                    entries.append(entry)
                    
                    if len(entries) >= 50:  # Limit fallback results
                        break
        
        return entries
    
    def _extract_names_from_text(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """Extract company and product names from entry text."""
        # Common patterns in the software list
        lines = text.split('\n')
        
        company_name = None
        product_name = None
        
        # First line often contains the company/product name
        if lines:
            first_line = lines[0].strip()
            
            # Look for patterns like "Company Name - Product Name"
            if ' - ' in first_line:
                parts = first_line.split(' - ', 1)
                company_name = parts[0].strip()
                product_name = parts[1].strip()
            elif ' by ' in first_line:
                # Pattern like "Product Name by Company Name"
                parts = first_line.split(' by ', 1)
                product_name = parts[0].strip()
                company_name = parts[1].strip()
            else:
                # Use the whole first line as company name
                company_name = first_line
        
        return company_name, product_name
    
    def save_urls_to_file(self, entries: List[Dict[str, str]], output_file: Path, job_id: Optional[str] = None) -> None:
        """Save scraped URLs to a text file."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            f.write(f"# HMRC Making Tax Digital Software Vendor URLs\n")
            f.write(f"# Scraped {len(entries)} entries\n")
            if job_id:
                f.write(f"# Job ID: {job_id}\n")
            f.write(f"\n")
            
            for entry in entries:
                f.write(f"# Company: {entry['company_name']}\n")
                f.write(f"# Product: {entry['product_name']}\n")
                f.write(f"{entry['website_url']}\n\n")
        
        logger.info("urls_saved_to_file", file=str(output_file), count=len(entries), job_id=job_id)
    
    def save_urls_minimal(self, entries: List[Dict[str, str]], output_file: Path, unique_only: bool = True, job_id: Optional[str] = None) -> None:
        """Save URLs to file in minimal format - just URLs, one per line."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        if unique_only:
            # Get unique domains
            unique_urls = self.get_unique_domains(entries)
            urls_to_save = unique_urls
        else:
            # Save all URLs (may have duplicates)
            urls_to_save = [entry['website_url'] for entry in entries if entry.get('website_url')]
        
        with open(output_file, 'w') as f:
            if job_id:
                f.write(f"# Job ID: {job_id}\n")
            for url in urls_to_save:
                f.write(f"{url}\n")
        
        logger.info("urls_saved_minimal", file=str(output_file), count=len(urls_to_save), unique_only=unique_only, job_id=job_id)
    
    def get_unique_domains(self, entries: List[Dict[str, str]]) -> List[str]:
        """Extract unique domains from the scraped URLs."""
        domains = set()
        
        for entry in entries:
            url = entry.get('website_url', '')
            if url:
                try:
                    parsed = urlparse(url)
                    domain = f"{parsed.scheme}://{parsed.netloc}"
                    domains.add(domain)
                except Exception:
                    # If URL parsing fails, use the original URL
                    domains.add(url)
        
        return sorted(list(domains))