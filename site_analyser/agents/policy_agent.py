"""Policy analysis agent using Agno framework."""

import re
from datetime import datetime
from typing import Optional, Dict, Any

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel
import structlog

from ..models.analysis import SiteAnalysisResult
from ..models.config import SiteAnalyserConfig

logger = structlog.get_logger()


class PolicyAnalysisResult(BaseModel):
    """Structured output for policy analysis."""
    privacy_policy_found: bool
    privacy_policy_url: Optional[str]
    terms_conditions_found: bool
    terms_conditions_url: Optional[str]
    analysis_confidence: float
    reasoning: str


class PolicyAnalysisTool:
    """Custom tool for policy detection and analysis."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        
        # Common patterns for privacy policy links
        self.privacy_patterns = [
            r'privacy\s*policy',
            r'privacy\s*statement',
            r'privacy\s*notice',
            r'data\s*protection',
            r'cookie\s*policy',
        ]
        
        # Common patterns for terms and conditions
        self.terms_patterns = [
            r'terms\s*(?:and|&|\+)?\s*conditions',
            r'terms\s*of\s*service',
            r'terms\s*of\s*use',
            r'legal\s*terms',
            r'user\s*agreement',
        ]
    
    def find_policy_links(self, html_content: str, base_url: str) -> Dict[str, Any]:
        """Find privacy policy and terms links in HTML content."""
        if not html_content:
            return {
                "privacy_policy": None,
                "terms_conditions": None,
                "confidence": 0.0
            }
        
        html_lower = html_content.lower()
        
        # Find privacy policy links
        privacy_url = None
        for pattern in self.privacy_patterns:
            matches = re.finditer(
                rf'<a[^>]*href=[\'"]([^\'"]*)[\'"][^>]*.*?{pattern}',
                html_lower,
                re.IGNORECASE | re.DOTALL
            )
            for match in matches:
                privacy_url = self._resolve_url(match.group(1), base_url)
                break
            if privacy_url:
                break
        
        # Find terms and conditions links
        terms_url = None
        for pattern in self.terms_patterns:
            matches = re.finditer(
                rf'<a[^>]*href=[\'"]([^\'"]*)[\'"][^>]*.*?{pattern}',
                html_lower,
                re.IGNORECASE | re.DOTALL
            )
            for match in matches:
                terms_url = self._resolve_url(match.group(1), base_url)
                break
            if terms_url:
                break
        
        # Calculate confidence based on findings
        confidence = 0.0
        if privacy_url:
            confidence += 0.5
        if terms_url:
            confidence += 0.5
        
        return {
            "privacy_policy": privacy_url,
            "terms_conditions": terms_url,
            "confidence": confidence
        }
    
    def _resolve_url(self, href: str, base_url: str) -> str:
        """Resolve relative URLs to absolute URLs."""
        if href.startswith(('http://', 'https://')):
            return href
        elif href.startswith('//'):
            return f"https:{href}"
        elif href.startswith('/'):
            base = base_url.rstrip('/')
            return f"{base}{href}"
        else:
            base = base_url.rstrip('/')
            return f"{base}/{href}"


class PolicyAgent:
    """Agno agent for policy analysis and compliance checking."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.analysis_tool = PolicyAnalysisTool(config)
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are a policy compliance specialist agent. Your expertise includes:
            
            1. GDPR and UK data protection requirements
            2. Privacy policy analysis and completeness
            3. Terms and conditions compliance
            4. Cookie policy requirements
            5. Legal compliance for UK businesses
            
            Your task is to:
            1. Identify privacy policy and terms & conditions links
            2. Assess the quality and completeness of policies
            3. Check for GDPR compliance indicators
            4. Flag missing or inadequate policies
            5. Provide compliance recommendations
            
            Look for common policy indicators:
            - Privacy Policy, Privacy Statement, Privacy Notice
            - Terms and Conditions, Terms of Service, Terms of Use
            - Cookie Policy, Data Protection Policy
            - Legal Terms, User Agreement
            
            Assess policy quality based on:
            - Accessibility and clarity
            - GDPR compliance elements
            - Data processing explanations
            - User rights information
            """,
            markdown=True,
            show_tool_calls=True,
            response_model=PolicyAnalysisResult,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_policies(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze a website for policy compliance."""
        logger.info("policy_agent_started", url=url)
        
        try:
            # Skip if no HTML content available
            if not result.html_content:
                logger.info("policy_agent_skipped", url=url, reason="no_html_content")
                result.privacy_policy = None
                result.terms_conditions = None
                return result
            
            # Use tool to find policy links
            policy_data = self.analysis_tool.find_policy_links(result.html_content, url)
            
            # Create analysis prompt
            analysis_prompt = f"""
            Analyze this website for policy compliance.
            Website URL: {url}
            
            Initial analysis found:
            - Privacy Policy: {"Found" if policy_data["privacy_policy"] else "Not found"}
            - Terms & Conditions: {"Found" if policy_data["terms_conditions"] else "Not found"}
            
            Please analyze the HTML content for:
            1. Privacy policy presence and accessibility
            2. Terms and conditions availability
            3. GDPR compliance indicators
            4. Cookie policy information
            5. Overall compliance assessment
            
            HTML snippet (first 3000 chars):
            {result.html_content[:3000]}
            """
            
            # Call the agent for enhanced analysis
            response = await self.agent.arun(analysis_prompt)
            
            # Process the response
            if isinstance(response, PolicyAnalysisResult):
                # Update result with findings
                result.privacy_policy = response.privacy_policy_url or policy_data["privacy_policy"]
                result.terms_conditions = response.terms_conditions_url or policy_data["terms_conditions"]
                
                logger.info(
                    "policy_agent_completed",
                    url=url,
                    has_privacy_policy=bool(result.privacy_policy),
                    has_terms_conditions=bool(result.terms_conditions),
                    confidence=response.analysis_confidence
                )
            else:
                # Fallback to tool-only analysis
                result.privacy_policy = policy_data["privacy_policy"]
                result.terms_conditions = policy_data["terms_conditions"]
                
                logger.info(
                    "policy_agent_fallback",
                    url=url,
                    has_privacy_policy=bool(result.privacy_policy),
                    has_terms_conditions=bool(result.terms_conditions)
                )
                
        except Exception as e:
            logger.error("policy_agent_exception", url=url, error=str(e))
            # Fallback to basic tool analysis
            if result.html_content:
                policy_data = self.analysis_tool.find_policy_links(result.html_content, url)
                result.privacy_policy = policy_data["privacy_policy"]
                result.terms_conditions = policy_data["terms_conditions"]
        
        return result