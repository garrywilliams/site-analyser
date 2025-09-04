"""BAML-powered comprehensive compliance analysis pipeline."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus, BatchJobResult
from ..models.config import SiteAnalyserConfig
from ..processors.baml_processor_factory import BAMLProcessorFactory
from ..agents.baml_analysis_coordinator import BAMLAnalysisCoordinator

logger = structlog.get_logger()


class BAMLCompliancePipeline:
    """
    Comprehensive BAML-powered compliance analysis pipeline combining:
    - Intelligent workflow orchestration
    - Multi-agent coordination
    - Type-safe AI processing
    - Quality assurance and validation
    """
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.version = "2.0.0-baml-pipeline"
        
        # Initialize BAML components
        self.processor_factory = BAMLProcessorFactory(config)
        self.agent_coordinator = BAMLAnalysisCoordinator(config)
        
        logger.info(
            "baml_pipeline_initialized",
            processors_count=len(self.processor_factory.list_processors()),
            baml_processors=len(self.processor_factory.get_baml_processors()),
            pipeline_version=self.version
        )
    
    async def analyze_single_site(self, url: str, use_agent_coordination: bool = True) -> SiteAnalysisResult:
        """
        Analyze a single site using BAML-powered comprehensive analysis.
        
        Args:
            url: The URL to analyze
            use_agent_coordination: Whether to use intelligent agent coordination
        
        Returns:
            Complete analysis result with all compliance assessments
        """
        start_time = datetime.now()
        
        try:
            logger.info("baml_single_site_analysis_started", url=url, agent_coordination=use_agent_coordination)
            
            # Initialize result
            result = SiteAnalysisResult(
                url=url,
                timestamp=start_time,
                status=AnalysisStatus.SUCCESS,
                site_loads=True,
                processing_duration_ms=0
            )
            
            if use_agent_coordination:
                # Use intelligent agent coordination for optimal analysis
                result = await self.agent_coordinator.coordinate_comprehensive_analysis(url, result)
            else:
                # Use comprehensive processor factory for systematic analysis
                result = await self.processor_factory.process_site_comprehensive(url, result)
            
            # Final processing
            result.processing_duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            logger.info(
                "baml_single_site_analysis_complete",
                url=url,
                status=result.status.value,
                duration_ms=result.processing_duration_ms,
                trademark_violations=len(result.trademark_violations),
                has_privacy_policy=result.privacy_policy is not None,
                has_terms=result.terms_conditions is not None
            )
            
            return result
            
        except Exception as e:
            logger.error("baml_single_site_analysis_failed", url=url, error=str(e))
            
            # Return failed result
            return SiteAnalysisResult(
                url=url,
                timestamp=start_time,
                status=AnalysisStatus.FAILED,
                site_loads=False,
                error_message=f"BAML analysis failed: {str(e)}",
                processing_duration_ms=int((datetime.now() - start_time).total_seconds() * 1000)
            )
    
    async def analyze_batch(
        self, 
        urls: List[str], 
        max_concurrent: Optional[int] = None,
        use_agent_coordination: bool = True
    ) -> BatchJobResult:
        """
        Analyze multiple sites concurrently using BAML-powered analysis.
        
        Args:
            urls: List of URLs to analyze
            max_concurrent: Maximum concurrent analyses (defaults to config value)
            use_agent_coordination: Whether to use intelligent agent coordination
        
        Returns:
            Batch analysis results with comprehensive compliance data
        """
        start_time = datetime.now()
        job_id = f"baml_batch_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        if max_concurrent is None:
            max_concurrent = self.config.processing_config.concurrent_requests
        
        logger.info(
            "baml_batch_analysis_started",
            job_id=job_id,
            total_urls=len(urls),
            max_concurrent=max_concurrent,
            agent_coordination=use_agent_coordination
        )
        
        # Initialize batch result
        batch_result = BatchJobResult(
            job_id=job_id,
            started_at=start_time,
            total_urls=len(urls),
            successful_analyses=0,
            failed_analyses=0,
            results=[]
        )
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_with_semaphore(url: str) -> SiteAnalysisResult:
            async with semaphore:
                return await self.analyze_single_site(url, use_agent_coordination)
        
        try:
            # Execute all analyses concurrently with limit
            tasks = [analyze_with_semaphore(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for url, result in zip(urls, results):
                if isinstance(result, Exception):
                    logger.error("baml_batch_site_failed", url=url, error=str(result))
                    
                    # Create failed result
                    failed_result = SiteAnalysisResult(
                        url=url,
                        timestamp=datetime.now(),
                        status=AnalysisStatus.FAILED,
                        site_loads=False,
                        error_message=f"Batch analysis exception: {str(result)}",
                        processing_duration_ms=0
                    )
                    batch_result.results.append(failed_result)
                    batch_result.failed_analyses += 1
                else:
                    batch_result.results.append(result)
                    if result.status == AnalysisStatus.SUCCESS:
                        batch_result.successful_analyses += 1
                    else:
                        batch_result.failed_analyses += 1
            
            batch_result.completed_at = datetime.now()
            
            logger.info(
                "baml_batch_analysis_complete",
                job_id=job_id,
                total_duration_ms=(batch_result.completed_at - batch_result.started_at).total_seconds() * 1000,
                successful=batch_result.successful_analyses,
                failed=batch_result.failed_analyses,
                success_rate=batch_result.successful_analyses / len(urls) if urls else 0
            )
            
        except Exception as e:
            logger.error("baml_batch_analysis_failed", job_id=job_id, error=str(e))
            batch_result.completed_at = datetime.now()
        
        return batch_result
    
    async def analyze_with_custom_workflow(
        self, 
        url: str, 
        priority_areas: List[str],
        custom_context: Optional[str] = None
    ) -> SiteAnalysisResult:
        """
        Analyze a site with custom workflow priorities using BAML intelligence.
        
        Args:
            url: The URL to analyze
            priority_areas: List of analysis priorities (e.g., ["trademark_violations", "gdpr_compliance"])
            custom_context: Additional context for analysis
        
        Returns:
            Analysis result optimized for specified priorities
        """
        start_time = datetime.now()
        
        logger.info(
            "baml_custom_workflow_started",
            url=url,
            priorities=priority_areas,
            has_custom_context=custom_context is not None
        )
        
        try:
            # Initialize result
            result = SiteAnalysisResult(
                url=url,
                timestamp=start_time,
                status=AnalysisStatus.SUCCESS,
                site_loads=True,
                processing_duration_ms=0
            )
            
            # Get BAML workflow recommendations with custom priorities
            workflow_coordinator = self.processor_factory.get_processor('workflow_coordinator')
            if workflow_coordinator:
                # This would use BAML workflow intelligence with custom priorities
                # Implementation depends on the specific processor API
                pass
            
            # For now, delegate to comprehensive analysis with metadata
            result = await self.agent_coordinator.coordinate_comprehensive_analysis(url, result)
            
            # Add custom workflow metadata
            if not hasattr(result, 'analysis_metadata'):
                result.analysis_metadata = {}
            
            result.analysis_metadata['custom_workflow'] = {
                "priority_areas": priority_areas,
                "custom_context": custom_context,
                "workflow_type": "baml_custom_priorities"
            }
            
            result.processing_duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            logger.info(
                "baml_custom_workflow_complete",
                url=url,
                duration_ms=result.processing_duration_ms,
                status=result.status.value
            )
            
            return result
            
        except Exception as e:
            logger.error("baml_custom_workflow_failed", url=url, error=str(e))
            
            return SiteAnalysisResult(
                url=url,
                timestamp=start_time,
                status=AnalysisStatus.FAILED,
                site_loads=False,
                error_message=f"Custom workflow failed: {str(e)}",
                processing_duration_ms=int((datetime.now() - start_time).total_seconds() * 1000)
            )
    
    def get_analysis_summary(self, result: SiteAnalysisResult) -> dict:
        """
        Generate a summary of BAML analysis results.
        
        Args:
            result: The analysis result to summarize
        
        Returns:
            Dictionary with analysis summary and key insights
        """
        summary = {
            "url": str(result.url),
            "analysis_status": result.status.value,
            "processing_duration_ms": result.processing_duration_ms,
            "timestamp": result.timestamp.isoformat(),
            
            # Core compliance findings
            "trademark_compliance": {
                "violations_found": len(result.trademark_violations),
                "high_confidence_violations": len([v for v in result.trademark_violations if v.confidence >= 0.8]),
                "violation_types": list(set(v.violation_type for v in result.trademark_violations))
            },
            
            "policy_compliance": {
                "privacy_policy_found": result.privacy_policy is not None,
                "terms_conditions_found": result.terms_conditions is not None,
                "privacy_policy_accessible": result.privacy_policy.accessible if result.privacy_policy else False,
                "terms_accessible": result.terms_conditions.accessible if result.terms_conditions else False
            },
            
            # Technical indicators
            "technical_status": {
                "site_loads": result.site_loads,
                "ssl_valid": result.ssl_analysis.ssl_valid if result.ssl_analysis else False,
                "load_time_ms": result.load_time_ms,
                "bot_protection_detected": result.bot_protection.detected if result.bot_protection else False
            },
            
            # Analysis completeness
            "analysis_completeness": {
                "has_screenshot": result.screenshot_path is not None and result.screenshot_path.exists() if result.screenshot_path else False,
                "has_html_content": result.html_content is not None,
                "content_analysis_available": bool(getattr(result, 'content_relevance', None)),
                "personal_data_analysis_available": bool(getattr(result, 'personal_data_analysis', None)),
                "completeness_analysis_available": bool(getattr(result, 'website_completeness', None)),
                "language_analysis_available": bool(getattr(result, 'language_analysis', None))
            }
        }
        
        # Add metadata if available
        if hasattr(result, 'analysis_metadata') and result.analysis_metadata:
            summary["metadata"] = result.analysis_metadata
        
        return summary
    
    def get_pipeline_stats(self) -> dict:
        """Get statistics about the BAML pipeline configuration."""
        return {
            "pipeline_version": self.version,
            "total_processors": len(self.processor_factory.list_processors()),
            "baml_processors": self.processor_factory.get_baml_processors(),
            "non_baml_processors": [p for p in self.processor_factory.list_processors() 
                                   if p not in self.processor_factory.get_baml_processors()],
            "agent_coordination_available": True,
            "workflow_intelligence_available": True,
            "supported_analysis_types": [
                "trademark_violations",
                "policy_compliance", 
                "content_relevance",
                "personal_data_practices",
                "website_completeness",
                "language_capabilities",
                "ssl_security",
                "bot_protection",
                "workflow_orchestration"
            ],
            "ai_providers": ["openai", "anthropic"],
            "fallback_mechanisms": ["provider_fallback", "coordination_fallback", "processing_fallback"]
        }


# Example usage functions for documentation
async def example_single_site_analysis():
    """Example of analyzing a single site with BAML."""
    from ..models.config import SiteAnalyserConfig, AIConfig
    
    config = SiteAnalyserConfig(
        urls=["https://example.com"],
        ai_config=AIConfig(
            provider="openai",
            model="gpt-4o"
        )
    )
    
    pipeline = BAMLCompliancePipeline(config)
    result = await pipeline.analyze_single_site("https://example.com")
    
    summary = pipeline.get_analysis_summary(result)
    return summary


async def example_batch_analysis():
    """Example of batch analysis with BAML."""
    from ..models.config import SiteAnalyserConfig, AIConfig
    
    config = SiteAnalyserConfig(
        urls=["https://example1.com", "https://example2.com"],
        ai_config=AIConfig(provider="openai")
    )
    
    pipeline = BAMLCompliancePipeline(config)
    batch_result = await pipeline.analyze_batch([
        "https://example1.com",
        "https://example2.com",
        "https://example3.com"
    ])
    
    return {
        "job_id": batch_result.job_id,
        "success_rate": batch_result.successful_analyses / batch_result.total_urls,
        "results_count": len(batch_result.results)
    }


async def example_custom_workflow():
    """Example of custom workflow analysis with BAML."""
    from ..models.config import SiteAnalyserConfig, AIConfig
    
    config = SiteAnalyserConfig(
        urls=["https://example.com"],
        ai_config=AIConfig(provider="anthropic")
    )
    
    pipeline = BAMLCompliancePipeline(config)
    result = await pipeline.analyze_with_custom_workflow(
        "https://example.com",
        priority_areas=["trademark_violations", "gdpr_compliance", "content_relevance"],
        custom_context="Focus on UK tax service compliance"
    )
    
    return pipeline.get_analysis_summary(result)