"""Multi-agent coordinator using Agno framework."""

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.models.anthropic import Claude
from agno.tools.reasoning import ReasoningTools
from pydantic import BaseModel
import structlog

from ..models.analysis import SiteAnalysisResult, BatchJobResult, AnalysisStatus, BotProtectionAnalysis
from ..models.config import SiteAnalyserConfig
from ..processors.ssl_checker import SSLProcessor
from ..processors.bot_protection_detector import BotProtectionDetectorProcessor
from .web_scraper_agent import WebScraperAgent
from .trademark_agent import TrademarkAgent
from .policy_agent import PolicyAgent

logger = structlog.get_logger()


class AnalysisOrchestrationResult(BaseModel):
    """Structured output for analysis coordination decisions."""
    should_continue_analysis: bool
    skip_reasons: List[str]
    priority_adjustments: Dict[str, str]
    estimated_completion_time: int
    reasoning: str


class SiteAnalysisCoordinator:
    """Agno-based coordinator for multi-agent site analysis."""
    
    def __init__(self, config: SiteAnalyserConfig):
        self.config = config
        self.job_id = str(uuid.uuid4())
        
        # Initialize agents
        self.web_scraper = WebScraperAgent(config)
        self.trademark_agent = TrademarkAgent(config)
        self.policy_agent = PolicyAgent(config)
        
        # Initialize traditional processors for SSL and bot detection
        self.ssl_processor = SSLProcessor(config)
        self.bot_detector = BotProtectionDetectorProcessor(config)
        
        # Create coordinator agent
        if config.ai_config.provider == "openai":
            model = OpenAIChat(id="gpt-4o")
        else:
            model = Claude(id="claude-sonnet-4-20250514")
        
        self.coordinator = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""
            You are the Site Analysis Coordinator, responsible for orchestrating multi-agent
            analysis workflows. Your responsibilities include:
            
            1. WORKFLOW ORCHESTRATION
            - Coordinate web scraping, policy analysis, and trademark detection
            - Optimize analysis order based on site characteristics
            - Handle failures and retry strategies
            - Manage resource allocation and rate limiting
            
            2. DECISION MAKING
            - Determine which analyses to perform based on site status
            - Skip unnecessary analyses for failed sites
            - Prioritize high-risk trademark violations
            - Balance thoroughness with performance
            
            3. QUALITY ASSURANCE
            - Validate analysis results across agents
            - Ensure data consistency and completeness
            - Flag anomalies or suspicious results
            - Maintain analysis quality standards
            
            4. REPORTING
            - Aggregate results from all agents
            - Provide analysis summaries and insights
            - Flag compliance issues and violations
            - Generate actionable recommendations
            
            Make intelligent decisions about analysis workflow based on:
            - Site accessibility and loading status
            - Bot protection detection results
            - SSL certificate validity
            - Content availability for analysis
            """,
            markdown=True,
            show_tool_calls=True,
            response_model=AnalysisOrchestrationResult,
            monitoring=False  # Disable telemetry
        )
    
    async def analyze_sites(self) -> BatchJobResult:
        """Coordinate analysis of all configured sites."""
        batch_result = BatchJobResult(
            job_id=self.job_id,
            started_at=datetime.now(timezone.utc),
            total_urls=len(self.config.urls),
            successful_analyses=0,
            failed_analyses=0
        )
        
        logger.info(
            "coordinator_batch_started",
            job_id=self.job_id,
            total_urls=batch_result.total_urls,
            concurrent_requests=self.config.processing_config.concurrent_requests
        )
        
        # Ensure output directories exist
        self.config.output_config.results_directory.mkdir(parents=True, exist_ok=True)
        self.config.output_config.screenshots_directory.mkdir(parents=True, exist_ok=True)
        
        # Process URLs with concurrency control
        semaphore = asyncio.Semaphore(self.config.processing_config.concurrent_requests)
        
        async def analyze_single_site(url: str):
            async with semaphore:
                return await self._coordinate_site_analysis(url)
        
        # Process all URLs concurrently
        tasks = [analyze_single_site(str(url)) for url in self.config.urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            if isinstance(result, Exception):
                logger.error("site_analysis_exception", error=str(result))
                batch_result.failed_analyses += 1
            else:
                batch_result.results.append(result)
                if result.status == AnalysisStatus.SUCCESS:
                    batch_result.successful_analyses += 1
                else:
                    batch_result.failed_analyses += 1
        
        batch_result.completed_at = datetime.now(timezone.utc)
        
        # Save results
        await self._save_results(batch_result)
        
        logger.info(
            "coordinator_batch_completed",
            job_id=self.job_id,
            successful=batch_result.successful_analyses,
            failed=batch_result.failed_analyses,
            duration_seconds=(batch_result.completed_at - batch_result.started_at).total_seconds()
        )
        
        return batch_result
    
    async def _coordinate_site_analysis(self, url: str) -> SiteAnalysisResult:
        """Coordinate analysis of a single site through multiple agents."""
        start_time = datetime.now(timezone.utc)
        
        result = SiteAnalysisResult(
            url=url,
            timestamp=start_time,
            status=AnalysisStatus.SUCCESS,
            site_loads=False,
            processing_duration_ms=0
        )
        
        logger.info("coordinator_site_started", url=url)
        
        try:
            # Step 1: Web scraping (always first)
            result = await self.web_scraper.scrape_site(url, result)
            
            # Step 2: SSL analysis (parallel with bot detection)
            result = await self.ssl_processor.process_with_retry(url, result)
            
            # Step 3: Bot protection detection
            result = await self.bot_detector.process_with_retry(url, result)
            
            # Step 4: Coordinate remaining analysis based on site status
            orchestration_decision = await self._get_orchestration_decision(url, result)
            
            if orchestration_decision.should_continue_analysis:
                # Step 5: Policy analysis (if site loaded successfully)
                if result.site_loads and result.html_content:
                    result = await self.policy_agent.analyze_policies(url, result)
                
                # Step 6: Trademark analysis (if screenshot available)
                if result.screenshot_path and result.screenshot_path.exists():
                    # Add rate limiting for AI requests
                    if self.config.processing_config.ai_request_delay_seconds > 0:
                        await asyncio.sleep(self.config.processing_config.ai_request_delay_seconds)
                    
                    result = await self.trademark_agent.analyze_trademark_violations(url, result)
            else:
                logger.info(
                    "coordinator_analysis_skipped",
                    url=url,
                    reasons=orchestration_decision.skip_reasons
                )
            
            # Calculate processing time
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            result.processing_duration_ms = int(processing_time)
            
            # Update processor versions
            result.processor_versions = {
                "WebScraperAgent": "1.0.0",
                "TrademarkAgent": "1.0.0", 
                "PolicyAgent": "1.0.0",
                "SSLProcessor": "1.0.0",
                "BotProtectionDetectorProcessor": "1.0.0",
                "SiteAnalysisCoordinator": "1.0.0"
            }
            
            logger.info(
                "coordinator_site_completed",
                url=url,
                status=result.status.value,
                site_loads=result.site_loads,
                trademark_violations=len(result.trademark_violations),
                processing_duration_ms=result.processing_duration_ms
            )
            
        except Exception as e:
            logger.error("coordinator_site_exception", url=url, error=str(e))
            result.status = AnalysisStatus.FAILED
            result.error_message = f"Coordinator error: {str(e)}"
        
        return result
    
    async def _get_orchestration_decision(self, url: str, result: SiteAnalysisResult) -> AnalysisOrchestrationResult:
        """Get AI-driven decision on how to proceed with analysis."""
        try:
            decision_prompt = f"""
            Make an orchestration decision for site analysis continuation.
            
            Site: {url}
            Current Status:
            - Site loads: {result.site_loads}
            - Has HTML content: {bool(result.html_content)}
            - Has screenshot: {bool(result.screenshot_path)}
            - SSL valid: {result.ssl_analysis.ssl_valid if result.ssl_analysis else "Unknown"}
            - Bot protection detected: {result.bot_protection.detected if result.bot_protection else "Unknown"}
            - Error message: {result.error_message or "None"}
            
            Should we continue with policy and trademark analysis?
            Consider: site accessibility, available data, analysis value, resource efficiency.
            """
            
            decision = await self.coordinator.arun(decision_prompt)
            
            if isinstance(decision, AnalysisOrchestrationResult):
                return decision
            else:
                # Fallback decision logic
                return self._make_fallback_decision(result)
                
        except Exception as e:
            logger.warning("orchestration_decision_failed", url=url, error=str(e))
            return self._make_fallback_decision(result)
    
    def _make_fallback_decision(self, result: SiteAnalysisResult) -> AnalysisOrchestrationResult:
        """Make a simple rule-based decision when AI coordination fails."""
        skip_reasons = []
        
        # Skip if site doesn't load and no content available
        if not result.site_loads and not result.html_content and not result.screenshot_path:
            skip_reasons.append("site_completely_inaccessible")
        
        # Skip if bot protection blocks all content
        if (result.bot_protection and 
            result.bot_protection.detected and 
            result.bot_protection.confidence > 0.7 and
            not result.html_content and
            not result.screenshot_path):
            skip_reasons.append("bot_protection_blocks_all_content")
        
        should_continue = len(skip_reasons) == 0
        
        return AnalysisOrchestrationResult(
            should_continue_analysis=should_continue,
            skip_reasons=skip_reasons,
            priority_adjustments={},
            estimated_completion_time=30000 if should_continue else 5000,
            reasoning=f"Rule-based decision: {'Continue' if should_continue else 'Skip'} analysis"
        )
    
    async def _save_results(self, batch_result: BatchJobResult) -> None:
        """Save batch results to JSON file."""
        if not self.config.output_config.json_output_file:
            return
        
        output_file = self.config.output_config.json_output_file
        output_data = batch_result.model_dump(mode="json")
        
        # Convert Path objects to strings for JSON serialization
        for result in output_data.get("results", []):
            if result.get("screenshot_path"):
                result["screenshot_path"] = str(result["screenshot_path"])
        
        import json
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        logger.info("coordinator_results_saved", output_file=str(output_file))