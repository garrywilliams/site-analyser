"""Base processor class."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from ..models.config import SiteAnalyserConfig

logger = structlog.get_logger()


class BaseProcessor(ABC):
    """Base class for all site analysis processors."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.version = "1.0.0"
    
    @abstractmethod
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Process a URL and update the analysis result."""
        pass
    
    async def process_with_retry(
        self, url: str, result: SiteAnalysisResult
    ) -> SiteAnalysisResult:
        """Process with retry logic."""
        max_retries = self.config.processing_config.max_retries
        retry_delay = self.config.processing_config.retry_delay_seconds
        
        for attempt in range(max_retries + 1):
            try:
                return await self.process(url, result)
            except Exception as e:
                if attempt == max_retries:
                    logger.error(
                        "processor_failed_final_attempt",
                        processor=self.__class__.__name__,
                        url=url,
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    result.status = AnalysisStatus.FAILED
                    result.error_message = f"{self.__class__.__name__}: {str(e)}"
                    return result
                
                logger.warning(
                    "processor_failed_retrying",
                    processor=self.__class__.__name__,
                    url=url,
                    attempt=attempt + 1,
                    error=str(e),
                )
                await asyncio.sleep(retry_delay)
        
        return result
    
    def _update_processor_version(self, result: SiteAnalysisResult) -> None:
        """Update the processor version in the result metadata."""
        result.processor_versions[self.__class__.__name__] = self.version