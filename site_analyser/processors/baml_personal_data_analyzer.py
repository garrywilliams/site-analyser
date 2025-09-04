"""BAML-powered personal data collection and GDPR compliance analyzer."""

from datetime import datetime
from pathlib import Path
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from .base import BaseProcessor
from ..baml_client.baml_client import b as baml_client
import baml_py
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class BAMLPersonalDataAnalyzerProcessor(BaseProcessor):
    """BAML-powered processor for personal data collection practices and GDPR compliance."""
    
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
        """Analyze personal data collection practices using BAML."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_personal_data_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Create BAML Image object from base64 encoded image
            import base64
            with open(result.screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Analyze personal data practices using BAML
            personal_data_result = await baml_client.AnalyzePersonalDataRequests(
                image=image,
                html_content=result.html_content,
                url=url
            )
            
            # Convert BAML data requests to our format
            data_requests = []
            for baml_request in personal_data_result.data_requests:
                data_requests.append({
                    "data_type": baml_request.data_type.value,
                    "purpose": baml_request.purpose,
                    "consent_mechanism": baml_request.consent_mechanism,
                    "required": baml_request.required
                })
            
            # Store results in the analysis result
            result.personal_data_analysis = {
                "compliance_level": personal_data_result.compliance_level.value,
                "compliance_score": personal_data_result.compliance_score,
                "data_requests": data_requests,
                "gdpr_indicators": personal_data_result.gdpr_indicators,
                "privacy_concerns": personal_data_result.privacy_concerns,
                "recommendations": personal_data_result.recommendations
            }
            
            logger.info(
                "baml_personal_data_analysis_complete",
                url=url,
                compliance_level=personal_data_result.compliance_level.value,
                compliance_score=personal_data_result.compliance_score,
                data_requests_count=len(data_requests),
                gdpr_indicators_count=len(personal_data_result.gdpr_indicators),
                privacy_concerns_count=len(personal_data_result.privacy_concerns),
                analysis_method="baml_personal_data_analyzer"
            )
            
        except Exception as e:
            logger.error("baml_personal_data_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result