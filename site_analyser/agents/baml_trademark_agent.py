"""BAML-powered trademark analysis agent combining Agno coordination with BAML functions."""

import asyncio
from datetime import datetime
import base64
import structlog
from pathlib import Path

from agno import Agent, ReasoningTools
from pydantic import BaseModel

from ..models.analysis import SiteAnalysisResult, TrademarkViolation, AnalysisStatus
from ..baml_client.baml_client import b as baml_client
import baml_py

logger = structlog.get_logger()


class TrademarkAnalysisResult(BaseModel):
    """Result model for trademark analysis combining BAML and Agno."""
    violations: list[TrademarkViolation] = []
    risk_assessment: str = ""
    confidence_summary: str = ""
    recommendations: list[str] = []
    analysis_method: str = "baml_agno_hybrid"
    processing_duration_ms: int = 0


class BAMLTrademarkAgent:
    """BAML-powered trademark analysis agent with Agno coordination."""
    
    def __init__(self, config):
        self.config = config
        self.version = "2.0.0-baml-agno"
        
        # Configure BAML clients with API keys
        if hasattr(config.ai_config, 'api_key') and config.ai_config.api_key:
            import os
            if config.ai_config.provider == "openai":
                os.environ["OPENAI_API_KEY"] = config.ai_config.api_key
            elif config.ai_config.provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = config.ai_config.api_key
        
        # Initialize Agno agent for coordination and reasoning
        from agno import Model
        
        model_name = config.ai_config.model if hasattr(config.ai_config, 'model') else "gpt-4o"
        provider = config.ai_config.provider if hasattr(config.ai_config, 'provider') else "openai"
        
        if provider == "openai":
            model = Model("openai:" + model_name)
        elif provider == "anthropic":
            model = Model("anthropic:" + model_name)
        else:
            model = Model("openai:gpt-4o")  # Default fallback
        
        self.agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""You are a UK trademark compliance specialist working with BAML-powered analysis tools.

Your role is to:
1. Coordinate trademark violation detection using BAML functions
2. Analyze BAML results for accuracy and completeness  
3. Provide strategic insights about trademark risks
4. Generate actionable compliance recommendations

You have access to sophisticated BAML vision analysis that provides structured trademark violation detection. Use this data to provide expert analysis and recommendations.

Focus on:
- UK Government trademark violations (Crown logos, GOV.UK branding)
- HMRC trademark violations (official branding, color schemes)
- NHS and other department-specific violations
- Overall risk assessment and mitigation strategies

Be thorough but concise in your analysis.""",
            response_model=TrademarkAnalysisResult,
            monitoring=False
        )
    
    async def analyze_trademark_violations(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze trademark violations using BAML + Agno coordination."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_agno_trademark_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Step 1: Get BAML analysis results
            baml_violations = await self._get_baml_analysis(url, result)
            
            # Step 2: Use Agno agent to analyze and coordinate the BAML results
            analysis_context = self._build_analysis_context(url, result, baml_violations)
            
            agent_result = await self.agent.run_async(
                f"""Analyze the trademark compliance situation for {url}.

BAML Analysis Results:
{self._format_baml_results_for_agent(baml_violations)}

Website Context:
{analysis_context}

Please provide a comprehensive trademark analysis including:
1. Validation of detected violations
2. Risk assessment and severity analysis  
3. Strategic compliance recommendations
4. Priority actions for violation remediation

Consider the business context and provide practical, actionable guidance."""
            )
            
            # Step 3: Combine BAML violations with Agno insights
            result.trademark_violations = baml_violations
            
            # Add agent insights to metadata
            if not hasattr(result, 'analysis_metadata'):
                result.analysis_metadata = {}
            
            result.analysis_metadata['trademark_analysis'] = {
                "risk_assessment": agent_result.risk_assessment,
                "confidence_summary": agent_result.confidence_summary,
                "recommendations": agent_result.recommendations,
                "analysis_method": "baml_agno_hybrid",
                "violation_count": len(baml_violations),
                "high_confidence_violations": len([v for v in baml_violations if v.confidence >= 0.8])
            }
            
            logger.info(
                "baml_agno_trademark_analysis_complete",
                url=url,
                total_violations=len(baml_violations),
                high_confidence_violations=len([v for v in baml_violations if v.confidence >= 0.8]),
                risk_assessment=agent_result.risk_assessment[:50] + "..." if len(agent_result.risk_assessment) > 50 else agent_result.risk_assessment,
                analysis_method="baml_agno_hybrid"
            )
            
        except Exception as e:
            logger.error("baml_agno_trademark_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
        
        return result
    
    async def _get_baml_analysis(self, url: str, result: SiteAnalysisResult) -> list[TrademarkViolation]:
        """Get trademark violations from BAML analysis."""
        try:
            # Create BAML Image object
            with open(result.screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Get BAML analysis with fallback
            try:
                baml_result = await baml_client.AnalyzeUKGovernmentTrademarks(
                    image=image,
                    url=url,
                    context=self._build_baml_context(result)
                )
                
                # Convert BAML violations to our models
                violations = []
                for baml_violation in baml_result.violations:
                    coordinates = None
                    if baml_violation.coordinates:
                        coordinates = {
                            "x": baml_violation.coordinates.x,
                            "y": baml_violation.coordinates.y,
                            "width": baml_violation.coordinates.width,
                            "height": baml_violation.coordinates.height
                        }
                    
                    violations.append(TrademarkViolation(
                        violation_type=baml_violation.violation_type.value,
                        confidence=baml_violation.confidence_score,
                        description=baml_violation.description,
                        location=baml_violation.location,
                        coordinates=coordinates,
                        detected_at=datetime.now()
                    ))
                
                return violations
                
            except Exception as primary_error:
                # Fallback to Claude
                logger.warning("baml_primary_failed_trying_claude", url=url, error=str(primary_error))
                
                baml_result = await baml_client.AnalyzeUKGovTrademarksWithClaude(
                    image=image,
                    url=url,
                    context=self._build_baml_context(result)
                )
                
                # Convert Claude results similarly
                violations = []
                for baml_violation in baml_result.violations:
                    coordinates = None
                    if baml_violation.coordinates:
                        coordinates = {
                            "x": baml_violation.coordinates.x,
                            "y": baml_violation.coordinates.y,
                            "width": baml_violation.coordinates.width,
                            "height": baml_violation.coordinates.height
                        }
                    
                    violations.append(TrademarkViolation(
                        violation_type=baml_violation.violation_type.value,
                        confidence=baml_violation.confidence_score,
                        description=baml_violation.description,
                        location=baml_violation.location,
                        coordinates=coordinates,
                        detected_at=datetime.now()
                    ))
                
                return violations
                
        except Exception as e:
            logger.error("baml_violation_analysis_failed", url=url, error=str(e))
            return []
    
    def _build_baml_context(self, result: SiteAnalysisResult) -> str:
        """Build context for BAML analysis."""
        context_parts = []
        
        if result.ssl_analysis:
            context_parts.append(f"SSL Status: {'Valid' if result.ssl_analysis.ssl_valid else 'Invalid'}")
        
        if result.bot_protection and result.bot_protection.detected:
            context_parts.append(f"Bot Protection: {result.bot_protection.protection_type}")
        
        if result.load_time_ms:
            context_parts.append(f"Load Time: {result.load_time_ms}ms")
            
        return " | ".join(context_parts) if context_parts else None
    
    def _build_analysis_context(self, url: str, result: SiteAnalysisResult, violations: list) -> str:
        """Build context for Agno agent analysis."""
        context_parts = [f"Target URL: {url}"]
        
        if result.ssl_analysis:
            context_parts.append(f"SSL Certificate: {'Valid' if result.ssl_analysis.ssl_valid else 'Invalid'}")
            if result.ssl_analysis.ssl_issuer:
                context_parts.append(f"SSL Issuer: {result.ssl_analysis.ssl_issuer}")
        
        if result.bot_protection and result.bot_protection.detected:
            context_parts.append(f"Bot Protection Detected: {result.bot_protection.protection_type}")
        
        if result.load_time_ms:
            context_parts.append(f"Site Load Time: {result.load_time_ms}ms")
        
        context_parts.append(f"Total Violations Detected: {len(violations)}")
        
        high_confidence = len([v for v in violations if v.confidence >= 0.8])
        if high_confidence > 0:
            context_parts.append(f"High Confidence Violations: {high_confidence}")
        
        return "\\n".join(context_parts)
    
    def _format_baml_results_for_agent(self, violations: list[TrademarkViolation]) -> str:
        """Format BAML results for Agno agent consumption."""
        if not violations:
            return "No trademark violations detected by BAML analysis."
        
        formatted_results = []
        for i, violation in enumerate(violations, 1):
            violation_text = [
                f"Violation {i}:",
                f"  Type: {violation.violation_type}",
                f"  Confidence: {violation.confidence:.2f}",
                f"  Description: {violation.description}"
            ]
            
            if violation.location:
                violation_text.append(f"  Location: {violation.location}")
            
            if violation.coordinates:
                violation_text.append(f"  Coordinates: {violation.coordinates}")
            
            formatted_results.append("\\n".join(violation_text))
        
        return "\\n\\n".join(formatted_results)