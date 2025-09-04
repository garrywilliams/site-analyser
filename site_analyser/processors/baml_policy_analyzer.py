"""BAML-powered policy compliance detection processor."""

from datetime import datetime
from pathlib import Path
import structlog

from ..models.analysis import SiteAnalysisResult, PolicyLink, AnalysisStatus
from .base import BaseProcessor
from ..baml_client.baml_client import b as baml_client
import baml_py
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class BAMLPolicyAnalyzerProcessor(BaseProcessor):
    """BAML-powered processor for detecting privacy policies and terms & conditions."""
    
    def __init__(self, config, rate_limiter: AIRateLimiter = None):
        super().__init__(config)
        self.version = "2.0.0-baml"
        
        # Configure BAML clients with API keys from config
        if hasattr(config.ai_config, 'api_key') and config.ai_config.api_key:
            import os
            if config.ai_config.provider == "openai":
                os.environ["OPENAI_API_KEY"] = config.ai_config.api_key
            elif config.ai_config.provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = config.ai_config.api_key
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze for policy links using BAML."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_policy_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Create BAML Image object from base64 encoded image
            import base64
            with open(result.screenshot_path, 'rb') as f:
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
                result.privacy_policy = PolicyLink(
                    text=policy_result.privacy_policy.text,
                    url=policy_result.privacy_policy.url,
                    accessible=policy_result.privacy_policy.accessible,
                    found_method=policy_result.privacy_policy.found_method
                )
            
            if policy_result.terms_conditions:
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
                gdpr_indicators=len(policy_result.gdpr_compliance_indicators),
                analysis_method="baml_policy_analyzer"
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