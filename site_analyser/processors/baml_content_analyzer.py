"""BAML-powered content relevance and business legitimacy analyzer."""

from datetime import datetime
from pathlib import Path
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from .base import BaseProcessor
from ..baml_client.baml_client import b as baml_client
import baml_py
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class BAMLContentAnalyzerProcessor(BaseProcessor):
    """BAML-powered processor for content relevance and business legitimacy analysis."""
    
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
        """Analyze content relevance using BAML."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("baml_content_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Create BAML Image object from base64 encoded image
            import base64
            with open(result.screenshot_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            image = baml_py.Image.from_base64("image/png", image_data)
            
            # Build analysis context
            context = self._build_analysis_context(result)
            
            # Analyze content relevance using BAML
            content_result = await baml_client.AnalyzeContentRelevance(
                image=image,
                html_content=result.html_content,
                url=url,
                context=context
            )
            
            # Store results in the analysis result
            result.content_relevance = {
                "tax_service_relevance": content_result.tax_service_relevance.value,
                "relevance_score": content_result.relevance_score,
                "business_legitimacy": content_result.business_legitimacy.value,
                "legitimacy_score": content_result.legitimacy_score,
                "service_categories": content_result.service_categories,
                "professional_indicators": content_result.professional_indicators,
                "concerns": content_result.concerns,
                "recommendations": content_result.recommendations
            }
            
            logger.info(
                "baml_content_analysis_complete",
                url=url,
                tax_relevance=content_result.tax_service_relevance.value,
                relevance_score=content_result.relevance_score,
                business_legitimacy=content_result.business_legitimacy.value,
                legitimacy_score=content_result.legitimacy_score,
                service_categories_count=len(content_result.service_categories),
                concerns_count=len(content_result.concerns),
                analysis_method="baml_content_analyzer"
            )
            
        except Exception as e:
            logger.error("baml_content_analysis_failed", url=url, error=str(e))
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
            
        if result.site_loads:
            context_parts.append("Site Status: Accessible")
        else:
            context_parts.append(f"Site Status: Load Failed - {result.error_message}")
            
        return " | ".join(context_parts) if context_parts else None