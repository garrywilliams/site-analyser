"""BAML-powered trademark infringement detection processor."""

from datetime import datetime
from pathlib import Path
import structlog

from ..models.analysis import SiteAnalysisResult, TrademarkViolation, AnalysisStatus
from .base import BaseProcessor
from ..baml_client.baml_client import b as baml_client
import baml_py
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class BAMLTrademarkAnalyzerProcessor(BaseProcessor):
    """BAML-powered processor for detecting UK Government and HMRC trademark infringements."""
    
    def __init__(self, config, rate_limiter: AIRateLimiter = None):
        super().__init__(config)
        self.version = "2.0.0-baml"
        # BAML client is accessed via the 'b' object
        
        # Configure BAML clients with API keys from config
        if hasattr(config.ai_config, 'api_key') and config.ai_config.api_key:
            import os
            if config.ai_config.provider == "openai":
                os.environ["OPENAI_API_KEY"] = config.ai_config.api_key
            elif config.ai_config.provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = config.ai_config.api_key
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze screenshot for trademark infringements using BAML."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_trademark_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Convert screenshot to BAML Image object
            image_path = Path(result.screenshot_path)
            # Create BAML Image object from base64 encoded image
            import base64
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Analyze using primary BAML function (OpenAI GPT-4 Vision)
            try:
                analysis_result = await baml_client.AnalyzeUKGovernmentTrademarks(
                    image=image,
                    url=url,
                    context=self._build_analysis_context(result)
                )
                
                # Convert BAML results to our TrademarkViolation models
                result.trademark_violations = self._convert_baml_violations(analysis_result.violations)
                
                logger.info(
                    "baml_trademark_analysis_complete",
                    url=url,
                    total_violations=len(result.trademark_violations),
                    risk_level=analysis_result.risk_level.value,
                    analysis_method="baml_gpt4_vision",
                    high_confidence_violations=len([v for v in result.trademark_violations 
                                                  if v.confidence >= 0.8])
                )
                
            except Exception as primary_error:
                logger.warning(
                    "baml_primary_analysis_failed_trying_fallback",
                    url=url, 
                    error=str(primary_error)
                )
                
                # Fallback to Claude Vision if OpenAI fails
                try:
                    analysis_result = await baml_client.AnalyzeUKGovTrademarksWithClaude(
                        image=image,
                        url=url,
                        context=self._build_analysis_context(result)
                    )
                    
                    result.trademark_violations = self._convert_baml_violations(analysis_result.violations)
                    
                    logger.info(
                        "baml_trademark_analysis_complete_fallback",
                        url=url,
                        total_violations=len(result.trademark_violations),
                        risk_level=analysis_result.risk_level.value,
                        analysis_method="baml_claude_vision"
                    )
                    
                except Exception as fallback_error:
                    logger.error(
                        "baml_analysis_completely_failed",
                        url=url,
                        primary_error=str(primary_error),
                        fallback_error=str(fallback_error)
                    )
                    if result.status != AnalysisStatus.FAILED:
                        result.status = AnalysisStatus.PARTIAL
                    
        except Exception as e:
            logger.error("baml_trademark_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result
    
    def _build_analysis_context(self, result: SiteAnalysisResult) -> str:
        """Build context information for BAML analysis."""
        context_parts = []
        
        if result.ssl_analysis:
            context_parts.append(f"SSL Status: {'Valid' if result.ssl_analysis.ssl_valid else 'Invalid'}")
        
        if result.bot_protection and result.bot_protection.detected:
            context_parts.append(f"Bot Protection: {result.bot_protection.protection_type}")
        
        if result.load_time_ms:
            context_parts.append(f"Load Time: {result.load_time_ms}ms")
            
        return " | ".join(context_parts) if context_parts else None
    
    def _convert_baml_violations(self, baml_violations) -> list[TrademarkViolation]:
        """Convert BAML violation objects to our TrademarkViolation models."""
        violations = []
        
        for baml_violation in baml_violations:
            # Convert BAML confidence enum to float
            confidence_score = baml_violation.confidence_score
            
            # Ensure confidence is within valid range
            if confidence_score < 0.0:
                confidence_score = 0.0
            elif confidence_score > 1.0:
                confidence_score = 1.0
            
            # Convert bounding box if present
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
                confidence=confidence_score,
                description=baml_violation.description,
                location=baml_violation.location,
                coordinates=coordinates,
                detected_at=datetime.now()
            ))
        
        return violations


class BAMLPolicyAnalyzerProcessor(BaseProcessor):
    """BAML-powered processor for policy link detection and analysis."""
    
    def __init__(self, config, rate_limiter: AIRateLimiter = None):
        super().__init__(config)
        self.version = "2.0.0-baml"
        # BAML client is accessed via the 'b' object
        
        # Configure BAML clients with API keys
        if hasattr(config.ai_config, 'api_key') and config.ai_config.api_key:
            import os
            if config.ai_config.provider == "openai":
                os.environ["OPENAI_API_KEY"] = config.ai_config.api_key
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze for policy links using BAML."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_policy_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Convert screenshot to BAML Image object
            image_path = Path(result.screenshot_path)
            # Create BAML Image object from base64 encoded image
            import base64
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Analyze policies using BAML
            policy_result = await baml_client.AnalyzePolicyLinks(
                image=image,
                html_content=result.html_content,
                url=url
            )
            
            # Convert BAML policy results to our models
            if policy_result.privacy_policy:
                from ..models.analysis import PolicyLink
                result.privacy_policy = PolicyLink(
                    text=policy_result.privacy_policy.text,
                    url=policy_result.privacy_policy.url,
                    accessible=policy_result.privacy_policy.accessible,
                    found_method=policy_result.privacy_policy.found_method
                )
            
            if policy_result.terms_conditions:
                from ..models.analysis import PolicyLink
                result.terms_conditions = PolicyLink(
                    text=policy_result.terms_conditions.text,
                    url=policy_result.terms_conditions.url,
                    accessible=policy_result.terms_conditions.accessible,
                    found_method=policy_result.terms_conditions.found_method
                )
            
            logger.info(
                "baml_policy_analysis_complete",
                url=url,
                privacy_policy_found=result.privacy_policy is not None,
                terms_found=result.terms_conditions is not None,
                compliance_score=policy_result.compliance_score,
                analysis_method="baml_gpt4_vision"
            )
            
        except Exception as e:
            logger.error("baml_policy_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result