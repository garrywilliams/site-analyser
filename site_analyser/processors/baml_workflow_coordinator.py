"""BAML-powered workflow coordination and analysis orchestration."""

from datetime import datetime
import structlog

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from .base import BaseProcessor
from ..baml_client.baml_client import b as baml_client
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class BAMLWorkflowCoordinatorProcessor(BaseProcessor):
    """BAML-powered processor for intelligent workflow coordination and analysis orchestration."""
    
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
    
    async def coordinate_analysis(self, url: str, context: str = None, priorities: list = None) -> dict:
        """Coordinate analysis workflow using BAML intelligence."""
        start_time = datetime.now()
        
        try:
            # Set default priorities if none provided
            if priorities is None:
                priorities = [
                    "trademark_violations",
                    "policy_compliance", 
                    "content_relevance",
                    "personal_data_practices"
                ]
            
            # Use BAML to coordinate the analysis workflow
            orchestration_result = await baml_client.CoordinateAnalysisWorkflow(
                url=url,
                context=context,
                priorities=priorities
            )
            
            # Convert BAML results to dictionary format
            workflow_plan = {
                "recommended_sequence": [],
                "parallel_processing_groups": orchestration_result.parallel_processing_groups,
                "total_estimated_duration": orchestration_result.total_estimated_duration,
                "risk_assessment": orchestration_result.risk_assessment,
                "resource_allocation": orchestration_result.resource_allocation,
                "quality_assurance_steps": orchestration_result.quality_assurance_steps,
                "recommendations": orchestration_result.recommendations
            }
            
            # Convert analysis tasks to dictionary format
            for task in orchestration_result.recommended_sequence:
                workflow_plan["recommended_sequence"].append({
                    "task_type": task.task_type,
                    "priority": task.priority.value,
                    "estimated_duration": task.estimated_duration,
                    "dependencies": task.dependencies,
                    "resource_requirements": task.resource_requirements
                })
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(
                "baml_workflow_coordination_complete",
                url=url,
                total_tasks=len(workflow_plan["recommended_sequence"]),
                parallel_groups=len(workflow_plan["parallel_processing_groups"]),
                estimated_duration=workflow_plan["total_estimated_duration"],
                risk_level=workflow_plan["risk_assessment"],
                processing_time_ms=int(processing_time),
                analysis_method="baml_workflow_coordinator"
            )
            
            return workflow_plan
            
        except Exception as e:
            logger.error("baml_workflow_coordination_failed", url=url, error=str(e))
            # Return default workflow plan on error
            return self._get_default_workflow_plan(priorities)
    
    def _get_default_workflow_plan(self, priorities: list) -> dict:
        """Return a default workflow plan when BAML coordination fails."""
        return {
            "recommended_sequence": [
                {
                    "task_type": priority,
                    "priority": "MEDIUM",
                    "estimated_duration": 30000,  # 30 seconds default
                    "dependencies": [],
                    "resource_requirements": ["screenshot", "ai_vision"]
                }
                for priority in priorities
            ],
            "parallel_processing_groups": [priorities],  # Run all in parallel by default
            "total_estimated_duration": 120000,  # 2 minutes total
            "risk_assessment": "Medium - using fallback coordination",
            "resource_allocation": ["ai_vision_analysis", "concurrent_processing"],
            "quality_assurance_steps": ["error_handling", "timeout_protection"],
            "recommendations": ["Use default processing order", "Monitor for coordination improvements"]
        }
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Standard processor interface - delegates to coordinate_analysis."""
        start_time = datetime.now()
        
        try:
            # Build context from current result state
            context = self._build_context_from_result(result)
            
            # Coordinate workflow
            workflow_plan = await self.coordinate_analysis(url, context)
            
            # Store workflow plan in result metadata (if we want to track it)
            if not hasattr(result, 'processing_metadata'):
                result.processing_metadata = {}
            result.processing_metadata['workflow_plan'] = workflow_plan
            
        except Exception as e:
            logger.error("baml_workflow_processor_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result
    
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
            
        if result.trademark_violations:
            context_parts.append(f"Trademark Violations: {len(result.trademark_violations)}")
            
        return " | ".join(context_parts) if context_parts else "No prior analysis context available"