"""Factory for creating BAML-powered processors with intelligent coordination."""

import asyncio
from typing import Dict, List, Any
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from ..models.config import SiteAnalyserConfig

# Import all BAML processors
from .baml_trademark_analyzer import BAMLTrademarkAnalyzerProcessor
from .baml_policy_analyzer import BAMLPolicyAnalyzerProcessor
from .baml_content_analyzer import BAMLContentAnalyzerProcessor
from .baml_personal_data_analyzer import BAMLPersonalDataAnalyzerProcessor
from .baml_website_completeness_analyzer import BAMLWebsiteCompletenessAnalyzerProcessor
from .baml_language_analyzer import BAMLLanguageAnalyzerProcessor
from .baml_workflow_coordinator import BAMLWorkflowCoordinatorProcessor

# Import non-AI processors that don't need BAML conversion
from .ssl_checker import SSLProcessor
from .web_scraper import WebScraperProcessor  
from .bot_protection_detector import BotProtectionDetectorProcessor

logger = structlog.get_logger()


class BAMLProcessorFactory:
    """Factory for creating and coordinating BAML-powered analysis processors."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.processors = {}
        self.workflow_coordinator = None
        self._initialize_processors()
    
    def _initialize_processors(self):
        """Initialize all BAML and non-AI processors."""
        # Non-AI processors (no BAML needed)
        self.processors['ssl_checker'] = SSLProcessor(self.config)
        self.processors['web_scraper'] = WebScraperProcessor(self.config)
        self.processors['bot_protection'] = BotProtectionDetectorProcessor(self.config)
        
        # BAML-powered AI processors
        self.processors['trademark_analyzer'] = BAMLTrademarkAnalyzerProcessor(self.config)
        self.processors['policy_analyzer'] = BAMLPolicyAnalyzerProcessor(self.config)
        self.processors['content_analyzer'] = BAMLContentAnalyzerProcessor(self.config)
        self.processors['personal_data_analyzer'] = BAMLPersonalDataAnalyzerProcessor(self.config)
        self.processors['completeness_analyzer'] = BAMLWebsiteCompletenessAnalyzerProcessor(self.config)
        self.processors['language_analyzer'] = BAMLLanguageAnalyzerProcessor(self.config)
        
        # Workflow coordinator
        self.workflow_coordinator = BAMLWorkflowCoordinatorProcessor(self.config)
    
    async def process_site_comprehensive(self, url: str, initial_result: SiteAnalysisResult = None) -> SiteAnalysisResult:
        """Process a site through all analysis stages with intelligent BAML coordination."""
        logger.info("baml_comprehensive_analysis_started", url=url)
        
        # Initialize result if not provided
        if initial_result is None:
            from datetime import datetime
            initial_result = SiteAnalysisResult(
                url=url,
                timestamp=datetime.now(),
                status=AnalysisStatus.SUCCESS,
                site_loads=True,
                processing_duration_ms=0
            )
        
        result = initial_result
        
        try:
            # Phase 1: Basic site analysis (non-AI)
            result = await self._run_basic_analysis(url, result)
            
            # Phase 2: Get intelligent workflow coordination from BAML
            workflow_plan = await self.workflow_coordinator.coordinate_analysis(
                url=url,
                context=self._build_context_from_result(result),
                priorities=self._get_analysis_priorities()
            )
            
            # Phase 3: Execute AI analysis based on BAML coordination
            result = await self._execute_coordinated_analysis(url, result, workflow_plan)
            
            logger.info(
                "baml_comprehensive_analysis_complete",
                url=url,
                final_status=result.status.value,
                total_duration_ms=result.processing_duration_ms,
                trademark_violations=len(result.trademark_violations),
                has_privacy_policy=result.privacy_policy is not None,
                has_terms=result.terms_conditions is not None,
                analysis_method="baml_comprehensive_processor"
            )
            
        except Exception as e:
            logger.error("baml_comprehensive_analysis_failed", url=url, error=str(e))
            result.status = AnalysisStatus.FAILED
            if not result.error_message:
                result.error_message = f"Comprehensive analysis failed: {str(e)}"
        
        return result
    
    async def _run_basic_analysis(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Run basic non-AI analysis first."""
        logger.info("baml_basic_analysis_started", url=url)
        
        # Run non-AI processors in sequence
        basic_processors = [
            'ssl_checker',
            'web_scraper',  # This gets screenshots and HTML
            'bot_protection'
        ]
        
        for processor_name in basic_processors:
            try:
                processor = self.processors[processor_name]
                result = await processor.process(url, result)
            except Exception as e:
                logger.warning(
                    "baml_basic_processor_failed",
                    url=url,
                    processor=processor_name,
                    error=str(e)
                )
                if result.status != AnalysisStatus.FAILED:
                    result.status = AnalysisStatus.PARTIAL
        
        return result
    
    async def _execute_coordinated_analysis(self, url: str, result: SiteAnalysisResult, workflow_plan: dict) -> SiteAnalysisResult:
        """Execute AI analysis based on BAML workflow coordination."""
        logger.info("baml_coordinated_ai_analysis_started", url=url, workflow_plan_tasks=len(workflow_plan["recommended_sequence"]))
        
        # Map task types to processor names
        task_processor_mapping = {
            'trademark_violations': 'trademark_analyzer',
            'trademark_analysis': 'trademark_analyzer',
            'policy_compliance': 'policy_analyzer',
            'policy_analysis': 'policy_analyzer',
            'content_relevance': 'content_analyzer',
            'content_analysis': 'content_analyzer',
            'personal_data_practices': 'personal_data_analyzer',
            'personal_data_analysis': 'personal_data_analyzer',
            'website_completeness': 'completeness_analyzer',
            'completeness_analysis': 'completeness_analyzer',
            'language_capabilities': 'language_analyzer',
            'language_analysis': 'language_analyzer'
        }
        
        # Execute analysis based on workflow plan
        try:
            # Check if we can run tasks in parallel
            if len(workflow_plan["parallel_processing_groups"]) > 0:
                result = await self._run_parallel_analysis(url, result, workflow_plan, task_processor_mapping)
            else:
                result = await self._run_sequential_analysis(url, result, workflow_plan, task_processor_mapping)
        
        except Exception as e:
            logger.error("baml_coordinated_analysis_failed", url=url, error=str(e))
            # Fallback to basic sequential analysis
            result = await self._run_fallback_analysis(url, result, task_processor_mapping)
        
        return result
    
    async def _run_parallel_analysis(self, url: str, result: SiteAnalysisResult, workflow_plan: dict, task_mapping: dict) -> SiteAnalysisResult:
        """Run analysis tasks in parallel groups."""
        for group_index, parallel_group in enumerate(workflow_plan["parallel_processing_groups"]):
            logger.info("baml_parallel_group_started", url=url, group_index=group_index, tasks=parallel_group)
            
            # Create tasks for this parallel group
            tasks = []
            for task_type in parallel_group:
                processor_name = task_mapping.get(task_type)
                if processor_name and processor_name in self.processors:
                    processor = self.processors[processor_name]
                    task = processor.process(url, result)
                    tasks.append((task_type, task))
            
            # Execute all tasks in this group concurrently
            if tasks:
                task_results = await asyncio.gather(
                    *[task for _, task in tasks], 
                    return_exceptions=True
                )
                
                # Process results and update main result
                for (task_type, _), task_result in zip(tasks, task_results):
                    if isinstance(task_result, Exception):
                        logger.warning("baml_parallel_task_failed", url=url, task_type=task_type, error=str(task_result))
                        if result.status != AnalysisStatus.FAILED:
                            result.status = AnalysisStatus.PARTIAL
                    else:
                        # Merge successful results
                        result = self._merge_analysis_results(result, task_result)
        
        return result
    
    async def _run_sequential_analysis(self, url: str, result: SiteAnalysisResult, workflow_plan: dict, task_mapping: dict) -> SiteAnalysisResult:
        """Run analysis tasks in recommended sequence."""
        for task in workflow_plan["recommended_sequence"]:
            task_type = task["task_type"]
            processor_name = task_mapping.get(task_type)
            
            if processor_name and processor_name in self.processors:
                try:
                    processor = self.processors[processor_name]
                    result = await processor.process(url, result)
                    logger.info("baml_sequential_task_complete", url=url, task_type=task_type)
                except Exception as e:
                    logger.warning("baml_sequential_task_failed", url=url, task_type=task_type, error=str(e))
                    if result.status != AnalysisStatus.FAILED:
                        result.status = AnalysisStatus.PARTIAL
        
        return result
    
    async def _run_fallback_analysis(self, url: str, result: SiteAnalysisResult, task_mapping: dict) -> SiteAnalysisResult:
        """Fallback analysis when coordination fails."""
        logger.info("baml_fallback_analysis_started", url=url)
        
        # Run all AI processors in default order
        ai_processors = [
            'trademark_analyzer',
            'policy_analyzer', 
            'content_analyzer',
            'personal_data_analyzer',
            'completeness_analyzer',
            'language_analyzer'
        ]
        
        for processor_name in ai_processors:
            if processor_name in self.processors:
                try:
                    processor = self.processors[processor_name]
                    result = await processor.process(url, result)
                except Exception as e:
                    logger.warning("baml_fallback_processor_failed", url=url, processor=processor_name, error=str(e))
                    if result.status != AnalysisStatus.FAILED:
                        result.status = AnalysisStatus.PARTIAL
        
        return result
    
    def _merge_analysis_results(self, base_result: SiteAnalysisResult, new_result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Merge results from parallel processing."""
        # Merge trademark violations
        base_result.trademark_violations.extend(new_result.trademark_violations)
        
        # Update policy links if found
        if new_result.privacy_policy and not base_result.privacy_policy:
            base_result.privacy_policy = new_result.privacy_policy
        if new_result.terms_conditions and not base_result.terms_conditions:
            base_result.terms_conditions = new_result.terms_conditions
        
        # Update analysis fields
        if new_result.content_relevance:
            base_result.content_relevance = new_result.content_relevance
        if new_result.personal_data_analysis:
            base_result.personal_data_analysis = new_result.personal_data_analysis
        if new_result.website_completeness:
            base_result.website_completeness = new_result.website_completeness
        if new_result.language_analysis:
            base_result.language_analysis = new_result.language_analysis
        
        # Update processing duration
        base_result.processing_duration_ms += new_result.processing_duration_ms
        
        # Update processor versions
        base_result.processor_versions.update(new_result.processor_versions)
        
        # Keep the worst status
        if new_result.status == AnalysisStatus.FAILED:
            base_result.status = AnalysisStatus.FAILED
        elif new_result.status == AnalysisStatus.PARTIAL and base_result.status == AnalysisStatus.SUCCESS:
            base_result.status = AnalysisStatus.PARTIAL
        
        return base_result
    
    def _build_context_from_result(self, result: SiteAnalysisResult) -> str:
        """Build context string from current analysis result."""
        context_parts = []
        
        if result.ssl_analysis:
            context_parts.append(f"SSL: {'Valid' if result.ssl_analysis.ssl_valid else 'Invalid'}")
        
        if result.bot_protection and result.bot_protection.detected:
            context_parts.append(f"Bot Protection: {result.bot_protection.protection_type}")
        
        if result.load_time_ms:
            context_parts.append(f"Load Time: {result.load_time_ms}ms")
            
        if not result.site_loads:
            context_parts.append(f"Site Issues: {result.error_message}")
            
        return " | ".join(context_parts) if context_parts else "Basic analysis complete"
    
    def _get_analysis_priorities(self) -> List[str]:
        """Get analysis priorities based on configuration."""
        # Default priorities - could be made configurable
        return [
            "trademark_violations",
            "policy_compliance",
            "content_relevance", 
            "personal_data_practices",
            "website_completeness",
            "language_capabilities"
        ]
    
    def get_processor(self, processor_name: str):
        """Get a specific processor by name."""
        return self.processors.get(processor_name)
    
    def list_processors(self) -> List[str]:
        """Get list of all available processors."""
        return list(self.processors.keys())
    
    def get_baml_processors(self) -> List[str]:
        """Get list of BAML-powered processors."""
        baml_processors = [
            'trademark_analyzer',
            'policy_analyzer',
            'content_analyzer',
            'personal_data_analyzer',
            'completeness_analyzer',
            'language_analyzer'
        ]
        return [p for p in baml_processors if p in self.processors]