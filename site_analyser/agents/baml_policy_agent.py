"""BAML-powered policy compliance agent combining Agno coordination with BAML functions."""

import asyncio
from datetime import datetime
import base64
import structlog
from pathlib import Path

from agno import Agent, ReasoningTools
from pydantic import BaseModel

from ..models.analysis import SiteAnalysisResult, PolicyLink, AnalysisStatus
from ..baml_client.baml_client import b as baml_client
import baml_py

logger = structlog.get_logger()


class PolicyAnalysisResult(BaseModel):
    """Result model for policy analysis combining BAML and Agno."""
    privacy_policy_found: bool = False
    terms_conditions_found: bool = False
    gdpr_compliance_assessment: str = ""
    privacy_score: float = 0.0
    compliance_recommendations: list[str] = []
    critical_issues: list[str] = []
    analysis_method: str = "baml_agno_hybrid"
    processing_duration_ms: int = 0


class BAMLPolicyAgent:
    """BAML-powered policy compliance agent with Agno coordination."""
    
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
            instructions="""You are a GDPR and privacy compliance specialist working with BAML-powered policy analysis tools.

Your role is to:
1. Interpret BAML policy detection results
2. Assess GDPR compliance status and gaps
3. Evaluate privacy policy quality and accessibility
4. Provide actionable compliance recommendations

You have access to BAML analysis that detects privacy policies, terms & conditions, and GDPR compliance indicators. Use this data to provide expert compliance assessment.

Focus on:
- GDPR compliance requirements for UK/EU data protection
- Privacy policy accessibility and quality
- Terms & conditions completeness
- Data subject rights compliance
- Cookie consent mechanisms
- Legal compliance recommendations

Provide practical, actionable guidance for achieving compliance.""",
            response_model=PolicyAnalysisResult,
            monitoring=False
        )
    
    async def analyze_policies(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze policy compliance using BAML + Agno coordination."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_agno_policy_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Step 1: Get BAML policy analysis results
            baml_policy_result = await self._get_baml_policy_analysis(url, result)
            
            # Step 2: Update result with BAML findings
            if baml_policy_result:
                if baml_policy_result.privacy_policy:
                    result.privacy_policy = PolicyLink(
                        text=baml_policy_result.privacy_policy.text,
                        url=baml_policy_result.privacy_policy.url,
                        accessible=baml_policy_result.privacy_policy.accessible,
                        found_method=baml_policy_result.privacy_policy.found_method
                    )
                
                if baml_policy_result.terms_conditions:
                    result.terms_conditions = PolicyLink(
                        text=baml_policy_result.terms_conditions.text,
                        url=baml_policy_result.terms_conditions.url,
                        accessible=baml_policy_result.terms_conditions.accessible,
                        found_method=baml_policy_result.terms_conditions.found_method
                    )
            
            # Step 3: Use Agno agent to provide expert compliance analysis
            analysis_context = self._build_analysis_context(url, result, baml_policy_result)
            
            agent_result = await self.agent.run_async(
                f"""Analyze the privacy and policy compliance situation for {url}.

BAML Policy Analysis Results:
{self._format_baml_policy_results_for_agent(baml_policy_result)}

Website Context:
{analysis_context}

Please provide a comprehensive policy compliance analysis including:
1. GDPR compliance assessment and gaps
2. Privacy policy quality and accessibility review
3. Data protection compliance status
4. Critical compliance issues requiring immediate attention
5. Prioritized recommendations for achieving full compliance

Consider UK/EU data protection requirements and provide practical, actionable guidance."""
            )
            
            # Step 4: Add agent insights to metadata
            if not hasattr(result, 'analysis_metadata'):
                result.analysis_metadata = {}
            
            result.analysis_metadata['policy_analysis'] = {
                "gdpr_compliance_assessment": agent_result.gdpr_compliance_assessment,
                "privacy_score": agent_result.privacy_score,
                "compliance_recommendations": agent_result.compliance_recommendations,
                "critical_issues": agent_result.critical_issues,
                "analysis_method": "baml_agno_hybrid",
                "privacy_policy_found": agent_result.privacy_policy_found,
                "terms_conditions_found": agent_result.terms_conditions_found
            }
            
            logger.info(
                "baml_agno_policy_analysis_complete",
                url=url,
                privacy_policy_found=result.privacy_policy is not None,
                terms_found=result.terms_conditions is not None,
                privacy_score=agent_result.privacy_score,
                critical_issues_count=len(agent_result.critical_issues),
                analysis_method="baml_agno_hybrid"
            )
            
        except Exception as e:
            logger.error("baml_agno_policy_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
        
        return result
    
    async def _get_baml_policy_analysis(self, url: str, result: SiteAnalysisResult):
        """Get policy analysis from BAML."""
        try:
            # Create BAML Image object
            with open(result.screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Get BAML policy analysis
            baml_result = await baml_client.AnalyzePolicyLinks(
                image=image,
                html_content=result.html_content,
                url=url
            )
            
            return baml_result
            
        except Exception as e:
            logger.error("baml_policy_analysis_failed", url=url, error=str(e))
            return None
    
    def _build_analysis_context(self, url: str, result: SiteAnalysisResult, baml_result) -> str:
        """Build context for Agno agent analysis."""
        context_parts = [f"Target URL: {url}"]
        
        if result.ssl_analysis:
            context_parts.append(f"SSL Certificate: {'Valid' if result.ssl_analysis.ssl_valid else 'Invalid'}")
        
        if result.bot_protection and result.bot_protection.detected:
            context_parts.append(f"Bot Protection: {result.bot_protection.protection_type}")
        
        if result.load_time_ms:
            context_parts.append(f"Site Load Time: {result.load_time_ms}ms")
        
        if result.html_content:
            context_parts.append(f"HTML Content Available: Yes ({len(result.html_content)} characters)")
        else:
            context_parts.append("HTML Content: Not available (screenshot analysis only)")
        
        if baml_result:
            context_parts.append(f"BAML Compliance Score: {baml_result.compliance_score:.2f}")
            context_parts.append(f"GDPR Indicators Found: {len(baml_result.gdpr_compliance_indicators)}")
            context_parts.append(f"Accessibility Issues: {len(baml_result.accessibility_issues)}")
        
        return "\\n".join(context_parts)
    
    def _format_baml_policy_results_for_agent(self, baml_result) -> str:
        """Format BAML policy results for Agno agent consumption."""
        if not baml_result:
            return "No policy analysis results available from BAML."
        
        formatted_results = []
        
        # Privacy Policy
        if baml_result.privacy_policy:
            pp = baml_result.privacy_policy
            formatted_results.append(f"Privacy Policy Found:")
            formatted_results.append(f"  Text: '{pp.text}'")
            formatted_results.append(f"  URL: {pp.url}")
            formatted_results.append(f"  Accessible: {pp.accessible}")
            formatted_results.append(f"  Detection Method: {pp.found_method}")
            if pp.location:
                formatted_results.append(f"  Location: {pp.location}")
        else:
            formatted_results.append("Privacy Policy: Not found")
        
        # Terms & Conditions
        if baml_result.terms_conditions:
            tc = baml_result.terms_conditions
            formatted_results.append(f"\\nTerms & Conditions Found:")
            formatted_results.append(f"  Text: '{tc.text}'")
            formatted_results.append(f"  URL: {tc.url}")
            formatted_results.append(f"  Accessible: {tc.accessible}")
            formatted_results.append(f"  Detection Method: {tc.found_method}")
            if tc.location:
                formatted_results.append(f"  Location: {tc.location}")
        else:
            formatted_results.append("\\nTerms & Conditions: Not found")
        
        # GDPR Compliance Indicators
        if baml_result.gdpr_compliance_indicators:
            formatted_results.append(f"\\nGDPR Compliance Indicators ({len(baml_result.gdpr_compliance_indicators)}):")
            for indicator in baml_result.gdpr_compliance_indicators:
                formatted_results.append(f"  • {indicator}")
        else:
            formatted_results.append("\\nGDPR Compliance Indicators: None detected")
        
        # Accessibility Issues
        if baml_result.accessibility_issues:
            formatted_results.append(f"\\nAccessibility Issues ({len(baml_result.accessibility_issues)}):")
            for issue in baml_result.accessibility_issues:
                formatted_results.append(f"  • {issue}")
        
        # Overall Compliance Score
        formatted_results.append(f"\\nOverall Compliance Score: {baml_result.compliance_score:.2f}/1.0")
        
        # Recommendations
        if baml_result.recommendations:
            formatted_results.append(f"\\nBAML Recommendations ({len(baml_result.recommendations)}):")
            for rec in baml_result.recommendations:
                formatted_results.append(f"  • {rec}")
        
        return "\\n".join(formatted_results)