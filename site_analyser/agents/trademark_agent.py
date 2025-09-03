"""Trademark analysis agent using Agno framework."""

import base64
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel
import structlog

from ..models.analysis import SiteAnalysisResult, TrademarkViolation
from ..models.config import SiteAnalyserConfig

logger = structlog.get_logger()


class TrademarkAnalysisResult(BaseModel):
    """Structured output for trademark analysis."""
    violations_detected: bool
    violations: List[dict]
    analysis_confidence: float
    reasoning: str


class TrademarkAnalysisTool:
    """Custom tool for trademark violation detection."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
    
    def encode_image(self, image_path: Path) -> str:
        """Encode image to base64 for vision models."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')


class TrademarkAgent:
    """Agno agent for trademark violation analysis."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.analysis_tool = TrademarkAnalysisTool(config)
        
        # Create the agent model
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        # Create the agent with trademark analysis instructions
        # Note: Disable structured output for now due to Agno compatibility issues
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions=f"""
            You are a trademark violation detection specialist. Your expertise includes:
            
            1. UK Government Visual Identity Guidelines
            2. HMRC branding and design standards
            3. Crown copyright and government symbols
            4. Unauthorized use of official logos and designs
            
            TRADEMARK VIOLATION CATEGORIES:
            - UK_GOVERNMENT_LOGO: Unauthorized use of UK Government logo
            - UK_GOVERNMENT_CROWN: Misuse of Crown symbol or royal coat of arms
            - UK_GOVERNMENT_COLORS: Using official government color schemes
            - UK_GOVERNMENT_TYPOGRAPHY: Copying government typography/fonts
            - HMRC_LOGO: Unauthorized HMRC logo usage
            - HMRC_BRANDING: Copying HMRC design elements
            - HMRC_IMPERSONATION: Impersonating HMRC services
            - OFFICIAL_ENDORSEMENT: Falsely implying government endorsement
            
            ANALYSIS CRITERIA:
            {self.config.ai_config.trademark_analysis_prompt}
            
            Your task: Analyze website screenshots for trademark violations. Provide:
            1. Detailed violation descriptions
            2. Confidence scores (0.0-1.0)
            3. Specific violation categories
            4. Evidence locations in the image
            
            IMPORTANT: If no violations are found, simply respond with "No trademark violations detected."
            If violations are found, list them clearly with violation type, description, and confidence score.
            """,
            markdown=True,
            show_tool_calls=True,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_trademark_violations(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze a website screenshot for trademark violations."""
        logger.info("trademark_agent_started", url=url)
        
        try:
            # Skip if no screenshot available
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.info("trademark_agent_skipped", url=url, reason="no_screenshot")
                result.trademark_violations = []
                return result
            
            # Prepare image for analysis
            image_base64 = self.analysis_tool.encode_image(result.screenshot_path)
            
            # Create analysis prompt with image
            analysis_prompt = f"""
            Analyze this website screenshot for trademark violations.
            Website URL: {url}
            
            Look for unauthorized use of:
            - UK Government logos, symbols, or branding
            - HMRC logos or official design elements
            - Crown symbols or royal coat of arms
            - Government color schemes (distinctive blue/white government styling)
            - Typography that mimics government websites
            - Any elements that could confuse users about official endorsement
            
            RESPOND IN THIS FORMAT:
            If no violations: "No trademark violations detected."
            
            If violations found, list each one as:
            VIOLATION: [type] - [description] - CONFIDENCE: [high/medium/low]
            
            Types to use: UK_GOVERNMENT_LOGO, UK_GOVERNMENT_CROWN, UK_GOVERNMENT_COLORS, 
            UK_GOVERNMENT_TYPOGRAPHY, HMRC_LOGO, HMRC_BRANDING, HMRC_IMPERSONATION, OFFICIAL_ENDORSEMENT
            """
            
            # Use the known working Agno approach directly
            agno_success = False
            response_text = None
            
            # Use Agno with base64 data URL format (the proven working approach)
            try:
                response = await self.agent.arun(
                    analysis_prompt,
                    images=[{"url": f"data:image/png;base64,{image_base64}"}]
                )
                response_text = str(response)
                logger.info("trademark_agent_response_received", url=url, response_type="agno_success")
                agno_success = True
            except Exception as agno_error:
                logger.error("trademark_agent_agno_failed", url=url, error=str(agno_error))
                result.trademark_violations = []
                return result
            
            # Process the Agno response
            
            # Process the Agno response for trademark violations
            violations = []
            logger.info("trademark_agent_response", url=url, response_preview=response_text[:300])
            
            # Parse the structured response
            if "no trademark violations detected" in response_text.lower():
                # Explicitly no violations
                logger.info("trademark_agent_no_violations", url=url)
            else:
                # Parse violation entries
                lines = response_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('VIOLATION:') or 'violation' in line.lower():
                        # Extract violation details
                        violation_type = "DETECTED_VIOLATION"
                        description = line[:200]  # Use the line as description
                        confidence = 0.5  # Default medium confidence
                        
                        # Try to extract confidence level
                        if 'CONFIDENCE:' in line.upper():
                            conf_part = line.upper().split('CONFIDENCE:')[-1].strip()
                            if 'HIGH' in conf_part:
                                confidence = 0.9
                            elif 'MEDIUM' in conf_part:
                                confidence = 0.6
                            elif 'LOW' in conf_part:
                                confidence = 0.3
                        
                        # Try to extract violation type
                        for vtype in ['UK_GOVERNMENT_LOGO', 'UK_GOVERNMENT_CROWN', 'UK_GOVERNMENT_COLORS', 
                                    'UK_GOVERNMENT_TYPOGRAPHY', 'HMRC_LOGO', 'HMRC_BRANDING', 
                                    'HMRC_IMPERSONATION', 'OFFICIAL_ENDORSEMENT']:
                            if vtype in line.upper():
                                violation_type = vtype
                                break
                        
                        violation = TrademarkViolation(
                            violation_type=violation_type,
                            description=description,
                            confidence=confidence,
                            location="Screenshot analysis",
                            detected_at=datetime.now()
                        )
                        violations.append(violation)
                        
                        # Log the violation found
                        logger.info("trademark_violation_detected", 
                                  url=url, 
                                  violation_type=violation_type, 
                                  confidence=confidence)
            
            result.trademark_violations = violations
            
            logger.info(
                "trademark_agent_completed",
                url=url,
                violations_found=len(violations),
                high_confidence_violations=len([v for v in violations if v.confidence >= 0.8])
            )
                
        except Exception as e:
            logger.error("trademark_agent_exception", url=url, error=str(e))
            result.trademark_violations = []
        
        return result