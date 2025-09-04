"""Website completeness assessment agent using Agno framework."""

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


class WebsiteCompletenessResult(BaseModel):
    """Structured result for website completeness analysis."""
    is_fully_functional: bool
    completeness_score: float
    missing_elements: List[str]
    construction_indicators: List[str]
    functional_areas: List[str]
    issues_found: List[str]
    reasoning: str


class WebsiteCompletenessAgent:
    """Agno agent for assessing website completeness and functionality."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent for completeness analysis
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are a website completeness and functionality assessment specialist.
            Your expertise includes:
            
            1. Business website standards and best practices
            2. Professional website completeness indicators
            3. Under-construction and placeholder content detection
            4. Essential business website elements
            5. User experience and navigation completeness
            
            ESSENTIAL WEBSITE ELEMENTS:
            - Complete navigation menu and site structure
            - Detailed service/product descriptions
            - Contact information and communication methods
            - About/company information pages
            - Professional design and branding
            - Functional forms and interactive elements
            - Working internal and external links
            - Complete footer with legal/company information
            
            SIGNS OF INCOMPLETE WEBSITES:
            - Lorem ipsum or placeholder text content
            - "Under construction" or "Coming soon" messages
            - Missing or broken navigation elements
            - Incomplete product/service descriptions
            - Missing contact information or company details
            - Non-functional forms or buttons
            - Placeholder images or generic stock photos
            - Incomplete page layouts or empty sections
            - Default template content not customized
            - Missing essential business pages
            
            FUNCTIONAL BUSINESS REQUIREMENTS:
            - Clear value proposition and service offerings
            - Professional presentation and design quality
            - Complete customer journey and information architecture
            - Accessible support and contact methods
            - Comprehensive business information
            
            Your task: Assess whether the website appears to be a complete, 
            fully-functional business website rather than a work-in-progress or placeholder.
            """,
            markdown=True,
            show_tool_calls=True,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_website_completeness(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze website completeness and functionality."""
        logger.info("website_completeness_agent_started", url=url)
        
        try:
            # Skip if no content available
            if not result.html_content:
                logger.info("completeness_skipped", url=url, reason="no_content")
                result.website_completeness = {
                    "is_fully_functional": False,
                    "completeness_score": 0.0,
                    "missing_elements": ["No content available for analysis"],
                    "construction_indicators": [],
                    "functional_areas": [],
                    "issues_found": ["Website content could not be retrieved"],
                    "reasoning": "Cannot assess completeness without content"
                }
                return result
            
            # Prepare content for analysis (truncate if too long)
            content_preview = result.html_content[:8000] if len(result.html_content) > 8000 else result.html_content
            
            analysis_prompt = f"""
            Assess this website for completeness and professional functionality:
            
            Website URL: {url}
            Content: {content_preview}
            
            Evaluate:
            1. Is this a complete, fully-functional business website?
            2. What essential elements are present or missing?
            3. Are there signs of construction or placeholder content?
            4. Does it appear professional and business-ready?
            5. What functional areas are working vs incomplete?
            
            Look for indicators of incomplete websites:
            - Lorem ipsum or placeholder text
            - "Under construction" messages
            - Missing navigation or broken structure
            - Incomplete service descriptions
            - Generic template content
            - Missing contact/company information
            
            RESPONSE FORMAT:
            FULLY_FUNCTIONAL: [YES/NO]
            COMPLETENESS_SCORE: [0.0-1.0]
            MISSING_ELEMENTS: [list what's missing or incomplete]
            CONSTRUCTION_SIGNS: [list any placeholder/construction indicators]
            FUNCTIONAL_AREAS: [list working sections/features]
            ISSUES: [list problems affecting functionality]
            ASSESSMENT: [detailed reasoning for completeness score]
            """
            
            # Use Agno for analysis
            response = await self.agent.arun(analysis_prompt)
            response_text = str(response)
            logger.info("completeness_response_received", url=url, response_type="agno_success")
            
            # Parse response
            completeness_data = self._parse_completeness_response(response_text)
            result.website_completeness = completeness_data
            
            logger.info("completeness_completed", 
                       url=url, 
                       is_functional=completeness_data["is_fully_functional"],
                       score=completeness_data["completeness_score"])
                
        except Exception as e:
            logger.error("website_completeness_agent_exception", url=url, error=str(e))
            result.website_completeness = {
                "is_fully_functional": False,
                "completeness_score": 0.0,
                "missing_elements": [],
                "construction_indicators": [],
                "functional_areas": [],
                "issues_found": [f"Analysis error: {str(e)}"],
                "reasoning": "Website completeness analysis could not be completed"
            }
        
        return result
    
    def _parse_completeness_response(self, response_text: str) -> dict:
        """Parse the Agno response for completeness data."""
        # Default values
        completeness_data = {
            "is_fully_functional": False,
            "completeness_score": 0.0,
            "missing_elements": [],
            "construction_indicators": [],
            "functional_areas": [],
            "issues_found": [],
            "reasoning": response_text[:500]  # Keep first 500 chars as reasoning
        }
        
        try:
            lines = response_text.split('\n')
            for line in lines:
                line = line.strip()
                
                if line.startswith('FULLY_FUNCTIONAL:'):
                    completeness_data["is_fully_functional"] = 'YES' in line.upper()
                
                elif line.startswith('COMPLETENESS_SCORE:'):
                    try:
                        score_text = line.split(':', 1)[1].strip()
                        completeness_data["completeness_score"] = float(score_text)
                    except (ValueError, IndexError):
                        pass
                
                elif line.startswith('MISSING_ELEMENTS:'):
                    elements_text = line.split(':', 1)[1].strip()
                    if elements_text and elements_text != '[list what\'s missing or incomplete]':
                        elements = [e.strip() for e in elements_text.replace('[', '').replace(']', '').split(',')]
                        completeness_data["missing_elements"] = [e for e in elements if e and len(e) > 2]
                
                elif line.startswith('CONSTRUCTION_SIGNS:'):
                    signs_text = line.split(':', 1)[1].strip()
                    if signs_text and signs_text != '[list any placeholder/construction indicators]':
                        signs = [s.strip() for s in signs_text.replace('[', '').replace(']', '').split(',')]
                        completeness_data["construction_indicators"] = [s for s in signs if s and len(s) > 2]
                
                elif line.startswith('FUNCTIONAL_AREAS:'):
                    areas_text = line.split(':', 1)[1].strip()
                    if areas_text and areas_text != '[list working sections/features]':
                        areas = [a.strip() for a in areas_text.replace('[', '').replace(']', '').split(',')]
                        completeness_data["functional_areas"] = [a for a in areas if a and len(a) > 2]
                
                elif line.startswith('ISSUES:'):
                    issues_text = line.split(':', 1)[1].strip()
                    if issues_text and issues_text != '[list problems affecting functionality]':
                        issues = [i.strip() for i in issues_text.replace('[', '').replace(']', '').split(',')]
                        completeness_data["issues_found"] = [i for i in issues if i and len(i) > 2]
                
                elif line.startswith('ASSESSMENT:'):
                    assessment_text = line.split(':', 1)[1].strip()
                    if assessment_text and assessment_text != '[detailed reasoning for completeness score]':
                        completeness_data["reasoning"] = assessment_text[:500]
        
        except Exception as e:
            logger.debug("completeness_response_parsing_error", error=str(e))
        
        return completeness_data