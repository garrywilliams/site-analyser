"""BAML-powered website completeness and professionalism analyzer."""

from datetime import datetime
from pathlib import Path
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from .base import BaseProcessor
from ..baml_client.baml_client import b as baml_client
import baml_py
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class BAMLWebsiteCompletenessAnalyzerProcessor(BaseProcessor):
    """BAML-powered processor for website completeness and professional presentation analysis."""
    
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
        """Analyze website completeness using BAML."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_completeness_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Create BAML Image object from base64 encoded image
            import base64
            with open(result.screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Analyze website completeness using BAML
            completeness_result = await baml_client.AnalyzeWebsiteCompleteness(
                image=image,
                html_content=result.html_content,
                url=url
            )
            
            # Store results in the analysis result
            result.website_completeness = {
                "completeness_level": completeness_result.completeness_level.value,
                "completeness_score": completeness_result.completeness_score,
                "missing_elements": completeness_result.missing_elements,
                "professional_indicators": completeness_result.professional_indicators,
                "trust_factors": completeness_result.trust_factors,
                "improvement_areas": completeness_result.improvement_areas,
                "recommendations": completeness_result.recommendations
            }
            
            logger.info(
                "baml_completeness_analysis_complete",
                url=url,
                completeness_level=completeness_result.completeness_level.value,
                completeness_score=completeness_result.completeness_score,
                missing_elements_count=len(completeness_result.missing_elements),
                professional_indicators_count=len(completeness_result.professional_indicators),
                trust_factors_count=len(completeness_result.trust_factors),
                improvement_areas_count=len(completeness_result.improvement_areas),
                analysis_method="baml_completeness_analyzer"
            )
            
        except Exception as e:
            logger.error("baml_completeness_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result