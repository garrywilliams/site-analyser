"""BAML-powered language capabilities and internationalization analyzer."""

from datetime import datetime
from pathlib import Path
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from .base import BaseProcessor
from ..baml_client.baml_client import b as baml_client
import baml_py
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class BAMLLanguageAnalyzerProcessor(BaseProcessor):
    """BAML-powered processor for language capabilities and internationalization analysis."""
    
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
        """Analyze language capabilities using BAML."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_language_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Create BAML Image object from base64 encoded image
            import base64
            with open(result.screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Analyze language capabilities using BAML
            language_result = await baml_client.AnalyzeLanguageCapabilities(
                image=image,
                html_content=result.html_content,
                url=url
            )
            
            # Store results in the analysis result
            result.language_analysis = {
                "primary_language": language_result.primary_language,
                "language_support": language_result.language_support.value,
                "language_quality": language_result.language_quality.value,
                "quality_score": language_result.quality_score,
                "supported_languages": language_result.supported_languages,
                "accessibility_features": language_result.accessibility_features,
                "internationalization_indicators": language_result.internationalization_indicators,
                "recommendations": language_result.recommendations
            }
            
            logger.info(
                "baml_language_analysis_complete",
                url=url,
                primary_language=language_result.primary_language,
                language_support=language_result.language_support.value,
                language_quality=language_result.language_quality.value,
                quality_score=language_result.quality_score,
                supported_languages_count=len(language_result.supported_languages),
                accessibility_features_count=len(language_result.accessibility_features),
                i18n_indicators_count=len(language_result.internationalization_indicators),
                analysis_method="baml_language_analyzer"
            )
            
        except Exception as e:
            logger.error("baml_language_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result