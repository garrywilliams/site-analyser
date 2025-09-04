"""Personal data request detection agent using Agno framework."""

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


class PersonalDataResult(BaseModel):
    """Structured result for personal data request analysis."""
    requests_personal_data: bool
    data_types_requested: List[str]
    request_methods: List[str]
    compliance_issues: List[str]
    gdpr_compliant: bool
    reasoning: str


class PersonalDataAgent:
    """Agno agent for detecting inappropriate personal data requests."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent for personal data analysis
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are a privacy and data protection specialist focusing on inappropriate personal data collection.
            Your expertise includes:
            
            1. GDPR and UK Data Protection Act requirements
            2. Legitimate vs inappropriate data collection practices
            3. Financial services data collection standards
            4. Tax service provider data requirements
            
            PERSONAL DATA TYPES TO MONITOR:
            - National Insurance numbers
            - Bank account details and sort codes
            - Credit card information
            - Full financial records or statements
            - Detailed personal financial information
            - Social Security numbers
            - Passport or driver's license numbers
            - Sensitive personal information beyond business needs
            
            LEGITIMATE DATA COLLECTION (allowed):
            - Company registration numbers
            - Business contact information
            - VAT registration numbers
            - Basic business details for service provision
            - Account creation credentials (email, password)
            - Business addresses for service delivery
            
            INAPPROPRIATE DATA COLLECTION (flag as violations):
            - Requesting personal financial data upfront
            - Asking for sensitive ID numbers before service agreement
            - Collecting personal data unrelated to tax services
            - Gathering excessive personal information
            - Missing clear data usage explanations
            - Lack of explicit consent mechanisms
            
            ANALYSIS FOCUS:
            - Look for forms requesting inappropriate personal data
            - Identify premature or excessive data collection
            - Check for proper consent and data usage explanations
            - Assess GDPR compliance in data collection practices
            
            Your task: Analyze website content and forms to identify inappropriate personal data requests.
            """,
            markdown=True,
            show_tool_calls=True,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_personal_data_requests(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze website for inappropriate personal data requests."""
        logger.info("personal_data_agent_started", url=url)
        
        try:
            # Skip if no content available
            if not result.html_content:
                logger.info("personal_data_skipped", url=url, reason="no_content")
                result.personal_data_analysis = {
                    "requests_personal_data": False,
                    "data_types_requested": [],
                    "request_methods": [],
                    "compliance_issues": ["No content available for analysis"],
                    "gdpr_compliant": True,
                    "reasoning": "Website content could not be retrieved"
                }
                return result
            
            # Focus on forms, input fields, and registration content
            content_preview = result.html_content[:8000] if len(result.html_content) > 8000 else result.html_content
            
            analysis_prompt = f"""
            Analyze this website for inappropriate personal data collection:
            
            Website URL: {url}
            Content: {content_preview}
            
            Look for:
            1. Forms requesting sensitive personal information
            2. Input fields for financial data, ID numbers, or personal details
            3. Registration processes requiring inappropriate data
            4. Data collection without proper consent or explanation
            5. Excessive data gathering beyond legitimate business needs
            
            ASSESS:
            - Are personal data requests appropriate for a tax service?
            - What specific data types are being requested?
            - Are there proper consent mechanisms and data usage explanations?
            - Does the data collection appear GDPR compliant?
            
            RESPONSE FORMAT:
            REQUESTS_DATA: [YES/NO]
            DATA_TYPES: [list specific data types requested]
            METHODS: [forms, registration, etc.]
            ISSUES: [list compliance problems]
            GDPR_COMPLIANT: [YES/NO]
            REASONING: [detailed explanation]
            """
            
            # Use Agno for analysis
            response = await self.agent.arun(analysis_prompt)
            response_text = str(response)
            logger.info("personal_data_response_received", url=url, response_type="agno_success")
            
            # Parse response
            data_analysis = self._parse_personal_data_response(response_text)
            result.personal_data_analysis = data_analysis
            
            logger.info("personal_data_completed", 
                       url=url, 
                       requests_data=data_analysis["requests_personal_data"],
                       gdpr_compliant=data_analysis["gdpr_compliant"])
                
        except Exception as e:
            logger.error("personal_data_agent_exception", url=url, error=str(e))
            result.personal_data_analysis = {
                "requests_personal_data": False,
                "data_types_requested": [],
                "request_methods": [],
                "compliance_issues": [f"Analysis error: {str(e)}"],
                "gdpr_compliant": True,
                "reasoning": "Personal data analysis could not be completed"
            }
        
        return result
    
    def _parse_personal_data_response(self, response_text: str) -> dict:
        """Parse the Agno response for personal data analysis."""
        # Default values
        data_analysis = {
            "requests_personal_data": False,
            "data_types_requested": [],
            "request_methods": [],
            "compliance_issues": [],
            "gdpr_compliant": True,
            "reasoning": response_text[:500]  # Keep first 500 chars as reasoning
        }
        
        try:
            lines = response_text.split('\n')
            for line in lines:
                line = line.strip()
                
                if line.startswith('REQUESTS_DATA:'):
                    data_analysis["requests_personal_data"] = 'YES' in line.upper()
                
                elif line.startswith('DATA_TYPES:'):
                    types_text = line.split(':', 1)[1].strip()
                    if types_text and types_text != '[list specific data types requested]':
                        # Split by common delimiters and clean up
                        types = [t.strip() for t in types_text.replace('[', '').replace(']', '').split(',')]
                        data_analysis["data_types_requested"] = [t for t in types if t and len(t) > 2]
                
                elif line.startswith('METHODS:'):
                    methods_text = line.split(':', 1)[1].strip()
                    if methods_text and methods_text != '[forms, registration, etc.]':
                        methods = [m.strip() for m in methods_text.replace('[', '').replace(']', '').split(',')]
                        data_analysis["request_methods"] = [m for m in methods if m and len(m) > 2]
                
                elif line.startswith('ISSUES:'):
                    issues_text = line.split(':', 1)[1].strip()
                    if issues_text and issues_text != '[list compliance problems]':
                        issues = [i.strip() for i in issues_text.replace('[', '').replace(']', '').split(',')]
                        data_analysis["compliance_issues"] = [i for i in issues if i and len(i) > 2]
                
                elif line.startswith('GDPR_COMPLIANT:'):
                    data_analysis["gdpr_compliant"] = 'YES' in line.upper()
                
                elif line.startswith('REASONING:'):
                    reasoning_text = line.split(':', 1)[1].strip()
                    if reasoning_text and reasoning_text != '[detailed explanation]':
                        data_analysis["reasoning"] = reasoning_text[:500]
        
        except Exception as e:
            logger.debug("personal_data_response_parsing_error", error=str(e))
        
        return data_analysis