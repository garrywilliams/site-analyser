"""Privacy policy and terms & conditions detection processor."""

import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx
import structlog

from ..models.analysis import SiteAnalysisResult, PolicyLink, AnalysisStatus
from .base import BaseProcessor
from ..utils.ai_client import AIClient
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class PolicyAnalyzerProcessor(BaseProcessor):
    """Processor for detecting and validating privacy policies and terms & conditions."""
    
    def __init__(self, config, rate_limiter: AIRateLimiter = None):
        super().__init__(config)
        self.version = "1.0.0"
        if rate_limiter is None:
            rate_limiter = AIRateLimiter(config.processing_config.ai_request_delay_seconds)
        self.ai_client = AIClient(config.ai_config, rate_limiter)
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze privacy policy and terms & conditions links."""
        start_time = datetime.now()
        
        try:
            if not result.html_content and not result.screenshot_path:
                logger.warning("policy_analysis_skipped_no_content", url=url)
                return result
            
            # Try HTML-based detection first (faster and more accurate)
            if result.html_content:
                await self._analyze_policies_from_html(url, result)
            
            # If we have a screenshot and didn't find policies in HTML, use AI vision
            if (not result.privacy_policy or not result.terms_conditions) and result.screenshot_path:
                await self._analyze_policies_from_screenshot(url, result)
            
            # Validate that found policy links are accessible
            await self._validate_policy_links(result)
            
            logger.info(
                "policy_analysis_complete",
                url=url,
                has_privacy_policy=bool(result.privacy_policy),
                has_terms_conditions=bool(result.terms_conditions),
                privacy_accessible=result.privacy_policy.accessible if result.privacy_policy else None,
                terms_accessible=result.terms_conditions.accessible if result.terms_conditions else None,
            )
            
        except Exception as e:
            logger.error("policy_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result
    
    async def _analyze_policies_from_html(self, url: str, result: SiteAnalysisResult) -> None:
        """Extract policy links from HTML content using BeautifulSoup."""
        soup = BeautifulSoup(result.html_content, 'html.parser')
        base_url = url
        
        # Privacy policy patterns
        privacy_patterns = [
            r'privacy\s*policy',
            r'privacy\s*statement',
            r'privacy\s*notice',
            r'data\s*protection',
            r'privacy'
        ]
        
        # Terms & conditions patterns
        terms_patterns = [
            r'terms\s*and\s*conditions',
            r'terms\s*of\s*service',
            r'terms\s*of\s*use',
            r'terms\s*&\s*conditions',
            r'legal\s*terms',
            r'user\s*agreement'
        ]
        
        # Find all links
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '').strip()
            text = link.get_text(strip=True).lower()
            
            if not href or not text:
                continue
            
            # Make URL absolute
            absolute_url = urljoin(base_url, href)
            
            # Check for privacy policy
            if not result.privacy_policy and any(re.search(pattern, text, re.IGNORECASE) for pattern in privacy_patterns):
                result.privacy_policy = PolicyLink(
                    text=link.get_text(strip=True),
                    url=absolute_url,
                    accessible=False,  # Will be validated later
                    found_method="html_parsing"
                )
            
            # Check for terms & conditions
            if not result.terms_conditions and any(re.search(pattern, text, re.IGNORECASE) for pattern in terms_patterns):
                result.terms_conditions = PolicyLink(
                    text=link.get_text(strip=True),
                    url=absolute_url,
                    accessible=False,  # Will be validated later
                    found_method="html_parsing"
                )
            
            # Stop if we found both
            if result.privacy_policy and result.terms_conditions:
                break
    
    async def _analyze_policies_from_screenshot(self, url: str, result: SiteAnalysisResult) -> None:
        """Use AI vision to detect policy links from screenshot."""
        if not result.screenshot_path or not result.screenshot_path.exists():
            return
        
        try:
            # Analyze for privacy policy if not found
            if not result.privacy_policy:
                privacy_response = await self.ai_client.analyze_image(
                    str(result.screenshot_path),
                    self.config.policy_prompts.privacy_policy_detection
                )
                
                privacy_links = self._parse_ai_policy_response(privacy_response, url)
                if privacy_links:
                    result.privacy_policy = PolicyLink(
                        text=privacy_links[0]['text'],
                        url=privacy_links[0]['url'],
                        accessible=False,
                        found_method="vision_analysis"
                    )
            
            # Analyze for terms & conditions if not found
            if not result.terms_conditions:
                terms_response = await self.ai_client.analyze_image(
                    str(result.screenshot_path),
                    self.config.policy_prompts.terms_conditions_detection
                )
                
                terms_links = self._parse_ai_policy_response(terms_response, url)
                if terms_links:
                    result.terms_conditions = PolicyLink(
                        text=terms_links[0]['text'],
                        url=terms_links[0]['url'],
                        accessible=False,
                        found_method="vision_analysis"
                    )
                    
        except Exception as e:
            logger.warning("ai_policy_detection_failed", url=url, error=str(e))
    
    def _parse_ai_policy_response(self, response: str, base_url: str) -> list[dict]:
        """Parse AI response for policy links."""
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                links = []
                if 'links' in data:
                    for link_data in data['links']:
                        if 'text' in link_data and 'url' in link_data:
                            # Try to construct full URL if relative
                            url = link_data['url']
                            if not url.startswith(('http://', 'https://')):
                                url = urljoin(base_url, url)
                            
                            links.append({
                                'text': link_data['text'],
                                'url': url
                            })
                
                return links
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("ai_policy_response_parse_failed", response=response[:200], error=str(e))
        
        return []
    
    async def _validate_policy_links(self, result: SiteAnalysisResult) -> None:
        """Validate that policy links are accessible."""
        timeout = self.config.processing_config.request_timeout_seconds
        
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True
        ) as client:
            
            # Check privacy policy
            if result.privacy_policy:
                try:
                    response = await client.head(str(result.privacy_policy.url))
                    result.privacy_policy.accessible = response.status_code < 400
                except httpx.RequestError:
                    result.privacy_policy.accessible = False
            
            # Check terms & conditions
            if result.terms_conditions:
                try:
                    response = await client.head(str(result.terms_conditions.url))
                    result.terms_conditions.accessible = response.status_code < 400
                except httpx.RequestError:
                    result.terms_conditions.accessible = False