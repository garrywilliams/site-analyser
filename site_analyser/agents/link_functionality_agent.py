"""Link functionality testing agent using Agno framework."""

import asyncio
import aiohttp
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel
import structlog

from ..models.analysis import SiteAnalysisResult
from ..models.config import SiteAnalyserConfig

logger = structlog.get_logger()


class LinkTestResult(BaseModel):
    """Result of testing a single link."""
    url: str
    status_code: Optional[int]
    is_working: bool
    error_message: Optional[str]
    response_time_ms: Optional[int]


class LinkFunctionalityResult(BaseModel):
    """Structured result for link functionality analysis."""
    total_links_found: int
    links_tested: int
    working_links: int
    broken_links: int
    link_test_results: List[Dict]
    functionality_score: float
    critical_links_broken: List[str]
    reasoning: str


class LinkFunctionalityAgent:
    """Agno agent for testing website link functionality."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent for link analysis
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are a website functionality and user experience specialist.
            Your expertise includes:
            
            1. Web accessibility and usability standards
            2. Critical website navigation elements
            3. Business website functionality requirements
            4. User journey and conversion path analysis
            
            CRITICAL LINKS TO PRIORITIZE:
            - Privacy Policy and Terms & Conditions (legal compliance)
            - Contact information and support links
            - Service pages and product information
            - Registration/sign-up processes
            - Payment and pricing pages
            - Download links for software/tools
            - Help and documentation sections
            
            LINK FUNCTIONALITY ASSESSMENT:
            - Categorize links by importance (critical, important, minor)
            - Assess impact of broken links on user experience
            - Evaluate navigation completeness
            - Check for circular references or dead ends
            - Identify missing essential pages
            
            COMPLIANCE REQUIREMENTS:
            - Privacy Policy must be accessible and functional
            - Terms & Conditions must be reachable
            - Contact methods must be available
            - Service descriptions must be accessible
            - Core business functionality must work
            
            Your task: Analyze link test results and assess website functionality completeness.
            Focus on business-critical links that affect compliance and user experience.
            """,
            markdown=True,
            show_tool_calls=True,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_link_functionality(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze and test website link functionality."""
        logger.info("link_functionality_agent_started", url=url)
        
        try:
            # Extract links from HTML content
            links = self._extract_links(url, result.html_content)
            logger.info("links_extracted", url=url, total_links=len(links))
            
            # Test a subset of important links (limit to avoid overwhelming the target)
            important_links = self._prioritize_links(links)[:10]  # Test top 10 most important
            
            # Test links functionality
            link_results = await self._test_links(important_links)
            
            # Use Agno to analyze the results
            functionality_analysis = await self._analyze_link_results(url, links, link_results)
            
            result.link_functionality = functionality_analysis
            
            logger.info("link_functionality_completed", 
                       url=url,
                       total_links=len(links),
                       tested_links=len(link_results),
                       working_links=sum(1 for r in link_results if r["is_working"]))
                
        except Exception as e:
            logger.error("link_functionality_agent_exception", url=url, error=str(e))
            result.link_functionality = {
                "total_links_found": 0,
                "links_tested": 0,
                "working_links": 0,
                "broken_links": 0,
                "link_test_results": [],
                "functionality_score": 0.0,
                "critical_links_broken": [],
                "reasoning": f"Link functionality analysis failed: {str(e)}"
            }
        
        return result
    
    def _extract_links(self, base_url: str, html_content: str) -> List[str]:
        """Extract links from HTML content."""
        import re
        
        if not html_content:
            return []
        
        # Find all href attributes
        href_pattern = r'href=["\']([^"\']+)["\']'
        matches = re.findall(href_pattern, html_content, re.IGNORECASE)
        
        links = []
        parsed_base = urlparse(base_url)
        base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
        
        for match in matches:
            try:
                # Convert relative URLs to absolute
                if match.startswith('/'):
                    full_url = base_domain + match
                elif match.startswith('http'):
                    full_url = match
                elif not match.startswith('#') and not match.startswith('mailto:'):
                    full_url = urljoin(base_url, match)
                else:
                    continue  # Skip anchors and mailto links
                
                # Only include HTTP/HTTPS links
                if full_url.startswith(('http://', 'https://')):
                    links.append(full_url)
            except:
                continue
        
        # Remove duplicates and sort
        return list(set(links))
    
    def _prioritize_links(self, links: List[str]) -> List[str]:
        """Prioritize links by importance for testing."""
        priority_keywords = [
            'privacy', 'terms', 'conditions', 'contact', 'about',
            'service', 'product', 'pricing', 'register', 'login',
            'download', 'help', 'support', 'legal'
        ]
        
        def get_priority_score(link):
            link_lower = link.lower()
            score = 0
            for keyword in priority_keywords:
                if keyword in link_lower:
                    score += 1
            return score
        
        # Sort by priority score (descending) then by URL length (ascending)
        return sorted(links, key=lambda x: (-get_priority_score(x), len(x)))
    
    async def _test_links(self, links: List[str]) -> List[Dict]:
        """Test a list of links for functionality."""
        results = []
        
        # Use semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests
        
        async def test_single_link(session, url):
            async with semaphore:
                try:
                    start_time = asyncio.get_event_loop().time()
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        end_time = asyncio.get_event_loop().time()
                        response_time = int((end_time - start_time) * 1000)
                        
                        return {
                            "url": url,
                            "status_code": response.status,
                            "is_working": 200 <= response.status < 400,
                            "error_message": None,
                            "response_time_ms": response_time
                        }
                except Exception as e:
                    return {
                        "url": url,
                        "status_code": None,
                        "is_working": False,
                        "error_message": str(e),
                        "response_time_ms": None
                    }
        
        # Test links concurrently
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=3)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [test_single_link(session, link) for link in links[:10]]  # Limit to 10 links
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and convert to dict
        valid_results = []
        for result in results:
            if isinstance(result, dict):
                valid_results.append(result)
            else:
                logger.debug("link_test_exception", error=str(result))
        
        return valid_results
    
    async def _analyze_link_results(self, url: str, all_links: List[str], test_results: List[Dict]) -> Dict:
        """Use Agno to analyze link test results."""
        working_count = sum(1 for r in test_results if r["is_working"])
        broken_count = len(test_results) - working_count
        
        # Identify critical broken links
        critical_broken = []
        for result in test_results:
            if not result["is_working"]:
                link_url = result["url"].lower()
                if any(keyword in link_url for keyword in ['privacy', 'terms', 'conditions', 'contact']):
                    critical_broken.append(result["url"])
        
        analysis_prompt = f"""
        Analyze website link functionality test results:
        
        Website: {url}
        Total links found: {len(all_links)}
        Links tested: {len(test_results)}
        Working links: {working_count}
        Broken links: {broken_count}
        Critical links broken: {len(critical_broken)}
        
        Test Results Summary:
        {chr(10).join([f"- {r['url']}: {'✅ Working' if r['is_working'] else '❌ Broken'} ({r['status_code'] or 'No response'})" for r in test_results[:5]])}
        
        Assess:
        1. Overall website functionality based on link test results
        2. Impact of broken links on user experience and compliance
        3. Critical navigation issues that need attention
        4. Functionality score (0.0-1.0) based on working essential links
        
        RESPONSE FORMAT:
        FUNCTIONALITY_SCORE: [0.0-1.0]
        CRITICAL_ISSUES: [list major problems]
        ASSESSMENT: [overall functionality assessment]
        """
        
        try:
            response = await self.agent.arun(analysis_prompt)
            response_text = str(response)
            
            # Parse functionality score
            functionality_score = working_count / len(test_results) if test_results else 0.0
            
            return {
                "total_links_found": len(all_links),
                "links_tested": len(test_results),
                "working_links": working_count,
                "broken_links": broken_count,
                "link_test_results": test_results,
                "functionality_score": functionality_score,
                "critical_links_broken": critical_broken,
                "reasoning": response_text[:500]
            }
        
        except Exception as e:
            logger.error("link_analysis_agno_failed", url=url, error=str(e))
            return {
                "total_links_found": len(all_links),
                "links_tested": len(test_results),
                "working_links": working_count,
                "broken_links": broken_count,
                "link_test_results": test_results,
                "functionality_score": working_count / len(test_results) if test_results else 0.0,
                "critical_links_broken": critical_broken,
                "reasoning": f"Link analysis completed. {working_count}/{len(test_results)} links working."
            }