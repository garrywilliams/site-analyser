"""Content relevance analysis agent using Agno framework."""

from datetime import datetime
from typing import List

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel
import structlog

from ..models.analysis import SiteAnalysisResult
from ..models.config import SiteAnalyserConfig

logger = structlog.get_logger()


class ContentRelevanceResult(BaseModel):
    """Structured result for content relevance analysis."""
    is_tax_relevant: bool
    relevance_score: float
    tax_services_mentioned: List[str]
    service_description: str
    compliance_issues: List[str]
    reasoning: str


class ContentRelevanceAgent:
    """Agno agent for analyzing content relevance to tax services."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent for content analysis
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are a tax services content relevance specialist. Your expertise includes:
            
            1. UK tax regulations and services (VAT, Corporation Tax, Income Tax, etc.)
            2. Making Tax Digital (MTD) requirements and bridging software
            3. HMRC approved services and terminology
            4. Tax preparation, filing, and compliance services
            5. Accounting and bookkeeping services related to tax obligations
            
            ANALYSIS CRITERIA:
            - Assess if website content is genuinely relevant to tax services
            - Identify specific tax services mentioned (VAT returns, MTD compliance, etc.)
            - Check for legitimate business tax solutions vs generic content
            - Evaluate service descriptions for authenticity and detail
            - Flag sites that appear to be placeholder/under construction
            - Identify misleading or vague service claims
            
            TAX SERVICE CATEGORIES TO LOOK FOR:
            - VAT return filing and bridging software
            - Making Tax Digital compliance solutions
            - Corporation tax preparation and filing
            - Income tax and self-assessment services
            - Payroll and PAYE services
            - Accounting software with tax features
            - Tax advisory and consultation services
            - HMRC-approved software and services
            
            COMPLIANCE REQUIREMENTS:
            - Content must clearly describe actual tax services offered
            - Services must be specific and detailed, not generic claims
            - Website should demonstrate genuine tax expertise
            - Avoid sites that are clearly under construction or placeholder content
            
            Your task: Analyze website content to determine relevance to legitimate tax services.
            Provide detailed assessment with evidence from the content.
            """,
            markdown=True,
            show_tool_calls=True,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_content_relevance(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze website content for relevance to tax services."""
        logger.info("content_relevance_agent_started", url=url)
        
        try:
            # Skip if no content available
            if not result.html_content:
                logger.info("content_relevance_skipped", url=url, reason="no_content")
                result.content_relevance = {
                    "is_tax_relevant": False,
                    "relevance_score": 0.0,
                    "tax_services_mentioned": [],
                    "service_description": "No content available for analysis",
                    "compliance_issues": ["No content available"],
                    "reasoning": "Website content could not be retrieved"
                }
                return result
            
            # Prepare content for analysis (truncate if too long)
            content_preview = result.html_content[:8000] if len(result.html_content) > 8000 else result.html_content
            
            analysis_prompt = f"""
            Analyze this website content for relevance to legitimate tax services:
            
            Website URL: {url}
            Content: {content_preview}
            
            Assess:
            1. Is this content genuinely relevant to tax services?
            2. What specific tax services are mentioned?
            3. How detailed and authentic are the service descriptions?
            4. Are there any compliance issues or red flags?
            5. Does this appear to be a functioning business website?
            
            RESPONSE FORMAT:
            TAX_RELEVANT: [YES/NO]
            RELEVANCE_SCORE: [0.0-1.0]
            TAX_SERVICES: [list specific services mentioned]
            DESCRIPTION: [brief summary of services offered]
            ISSUES: [list any compliance concerns]
            REASONING: [detailed explanation of assessment]
            """
            
            # Use Agno for analysis
            response = await self.agent.arun(analysis_prompt)
            response_text = str(response)
            logger.info("content_relevance_response_received", url=url, response_type="agno_success")
            
            # Parse response
            relevance_data = self._parse_relevance_response(response_text)
            result.content_relevance = relevance_data
            
            logger.info("content_relevance_completed", 
                       url=url, 
                       is_relevant=relevance_data["is_tax_relevant"],
                       score=relevance_data["relevance_score"])
                
        except Exception as e:
            logger.error("content_relevance_agent_exception", url=url, error=str(e))
            result.content_relevance = {
                "is_tax_relevant": False,
                "relevance_score": 0.0,
                "tax_services_mentioned": [],
                "service_description": "Analysis failed",
                "compliance_issues": [f"Analysis error: {str(e)}"],
                "reasoning": "Content analysis could not be completed"
            }
        
        return result
    
    def _parse_relevance_response(self, response_text: str) -> dict:
        """Parse the Agno response for content relevance data."""
        # Default values
        relevance_data = {
            "is_tax_relevant": False,
            "relevance_score": 0.0,
            "tax_services_mentioned": [],
            "service_description": "No clear service description found",
            "compliance_issues": [],
            "reasoning": response_text[:500]  # Keep first 500 chars as reasoning
        }
        
        try:
            lines = response_text.split('\n')
            for line in lines:
                line = line.strip()
                
                if line.startswith('TAX_RELEVANT:'):
                    relevance_data["is_tax_relevant"] = 'YES' in line.upper()
                
                elif line.startswith('RELEVANCE_SCORE:'):
                    try:
                        score_text = line.split(':', 1)[1].strip()
                        relevance_data["relevance_score"] = float(score_text)
                    except (ValueError, IndexError):
                        pass
                
                elif line.startswith('TAX_SERVICES:'):
                    services_text = line.split(':', 1)[1].strip()
                    if services_text and services_text != '[list specific services mentioned]':
                        # Split by common delimiters and clean up
                        services = [s.strip() for s in services_text.replace('[', '').replace(']', '').split(',')]
                        relevance_data["tax_services_mentioned"] = [s for s in services if s and len(s) > 2]
                
                elif line.startswith('DESCRIPTION:'):
                    desc_text = line.split(':', 1)[1].strip()
                    if desc_text and desc_text != '[brief summary of services offered]':
                        relevance_data["service_description"] = desc_text[:200]
                
                elif line.startswith('ISSUES:'):
                    issues_text = line.split(':', 1)[1].strip()
                    if issues_text and issues_text != '[list any compliance concerns]':
                        issues = [i.strip() for i in issues_text.replace('[', '').replace(']', '').split(',')]
                        relevance_data["compliance_issues"] = [i for i in issues if i and len(i) > 2]
                
                elif line.startswith('REASONING:'):
                    reasoning_text = line.split(':', 1)[1].strip()
                    if reasoning_text and reasoning_text != '[detailed explanation of assessment]':
                        relevance_data["reasoning"] = reasoning_text[:500]
        
        except Exception as e:
            logger.debug("relevance_response_parsing_error", error=str(e))
        
        return relevance_data