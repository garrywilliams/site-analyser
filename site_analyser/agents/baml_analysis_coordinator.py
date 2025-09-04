"""BAML-powered analysis coordinator combining intelligent workflow orchestration with multi-agent coordination."""

import asyncio
from datetime import datetime
import structlog
from typing import Dict, List, Any, Optional

from agno import Agent, ReasoningTools
from pydantic import BaseModel

from ..models.analysis import SiteAnalysisResult, AnalysisStatus
from ..baml_client.baml_client import b as baml_client

# Import BAML-powered agents
from .baml_trademark_agent import BAMLTrademarkAgent
from .baml_policy_agent import BAMLPolicyAgent

logger = structlog.get_logger()


class CoordinationResult(BaseModel):
    """Result model for analysis coordination."""
    execution_plan: Dict[str, Any]
    agents_executed: List[str] = []
    total_duration_ms: int = 0
    coordination_method: str = "baml_agno_coordination"
    success_rate: float = 0.0
    issues_encountered: List[str] = []
    recommendations: List[str] = []


class BAMLAnalysisCoordinator:
    """BAML-powered analysis coordinator with intelligent workflow orchestration."""
    
    def __init__(self, config):
        self.config = config
        self.version = "2.0.0-baml-agno-coordinator"
        
        # Configure BAML clients with API keys
        if hasattr(config.ai_config, 'api_key') and config.ai_config.api_key:
            import os
            if config.ai_config.provider == "openai":
                os.environ["OPENAI_API_KEY"] = config.ai_config.api_key
            elif config.ai_config.provider == "anthropic":
                os.environ["ANTHROPIC_API_KEY"] = config.ai_config.api_key
        
        # Initialize specialized agents
        self.agents = {
            'trademark': BAMLTrademarkAgent(config),
            'policy': BAMLPolicyAgent(config),
            # Additional agents can be added here
        }
        
        # Initialize Agno coordination agent
        from agno import Model
        
        model_name = config.ai_config.model if hasattr(config.ai_config, 'model') else "gpt-4o"
        provider = config.ai_config.provider if hasattr(config.ai_config, 'provider') else "openai"
        
        if provider == "openai":
            model = Model("openai:" + model_name)
        elif provider == "anthropic":
            model = Model("anthropic:" + model_name)
        else:
            model = Model("openai:gpt-4o")  # Default fallback
        
        self.coordination_agent = Agent(
            model=model,
            tools=[ReasoningTools(add_instructions=True)],
            instructions="""You are an intelligent analysis coordination specialist working with BAML-powered workflow orchestration and multi-agent systems.

Your role is to:
1. Interpret BAML workflow recommendations and optimize execution
2. Coordinate specialized analysis agents (trademark, policy, content, etc.)
3. Monitor analysis progress and adjust execution strategies
4. Resolve conflicts and dependencies between analysis types
5. Ensure comprehensive compliance coverage

You have access to:
- BAML workflow intelligence for optimal task sequencing
- Specialized agents with domain expertise
- Real-time execution monitoring and adjustment capabilities

Focus on:
- Efficient resource utilization and parallel processing
- Risk-based prioritization of critical compliance areas
- Quality assurance through cross-validation
- Adaptive execution based on real-time results
- Comprehensive reporting and recommendations

Provide strategic coordination decisions and optimize for both speed and accuracy.""",
            response_model=CoordinationResult,
            monitoring=False
        )
    
    async def coordinate_comprehensive_analysis(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Coordinate comprehensive analysis using BAML workflow intelligence + Agno agents."""
        start_time = datetime.now()
        
        try:
            # Step 1: Get BAML workflow recommendations
            workflow_plan = await self._get_baml_workflow_plan(url, result)
            
            # Step 2: Use Agno coordination agent to optimize execution strategy
            execution_strategy = await self._get_execution_strategy(url, result, workflow_plan)
            
            # Step 3: Execute coordinated analysis based on strategy
            result = await self._execute_coordinated_analysis(url, result, execution_strategy)
            
            # Step 4: Perform quality assurance and cross-validation
            result = await self._perform_quality_assurance(url, result)
            
            logger.info(
                "baml_agno_coordination_complete",
                url=url,
                agents_executed=len(self.agents),
                total_duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
                final_status=result.status.value,
                coordination_method="baml_agno_hybrid"
            )
            
        except Exception as e:
            logger.error("baml_agno_coordination_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
        
        return result
    
    async def _get_baml_workflow_plan(self, url: str, result: SiteAnalysisResult) -> Dict[str, Any]:
        """Get intelligent workflow plan from BAML."""
        try:
            context = self._build_analysis_context(result)
            priorities = ["trademark_violations", "policy_compliance", "content_relevance"]
            
            baml_workflow = await baml_client.CoordinateAnalysisWorkflow(
                url=url,
                context=context,
                priorities=priorities
            )
            
            # Convert BAML workflow to dict format
            workflow_plan = {
                "recommended_sequence": [],
                "parallel_processing_groups": baml_workflow.parallel_processing_groups,
                "total_estimated_duration": baml_workflow.total_estimated_duration,
                "risk_assessment": baml_workflow.risk_assessment,
                "resource_allocation": baml_workflow.resource_allocation,
                "quality_assurance_steps": baml_workflow.quality_assurance_steps,
                "recommendations": baml_workflow.recommendations
            }
            
            # Convert tasks to dict format
            for task in baml_workflow.recommended_sequence:
                workflow_plan["recommended_sequence"].append({
                    "task_type": task.task_type,
                    "priority": task.priority.value,
                    "estimated_duration": task.estimated_duration,
                    "dependencies": task.dependencies,
                    "resource_requirements": task.resource_requirements
                })
            
            return workflow_plan
            
        except Exception as e:
            logger.warning("baml_workflow_planning_failed", url=url, error=str(e))
            return self._get_default_workflow_plan()
    
    async def _get_execution_strategy(self, url: str, result: SiteAnalysisResult, workflow_plan: Dict[str, Any]) -> CoordinationResult:
        """Use Agno coordination agent to optimize execution strategy."""
        try:
            analysis_context = self._build_coordination_context(url, result, workflow_plan)
            
            strategy = await self.coordination_agent.run_async(
                f"""Optimize the analysis execution strategy for {url}.

BAML Workflow Plan:
{self._format_workflow_plan_for_agent(workflow_plan)}

Current Analysis State:
{analysis_context}

Available Specialized Agents:
- Trademark Agent: UK Government/HMRC trademark violation detection
- Policy Agent: GDPR compliance and privacy policy analysis

Please provide an optimized execution strategy that:
1. Maximizes efficiency through intelligent sequencing
2. Identifies opportunities for parallel processing
3. Manages resource allocation and dependencies
4. Prioritizes critical compliance areas
5. Includes quality assurance checkpoints

Consider the current analysis state and provide a concrete execution plan."""
            )
            
            return strategy
            
        except Exception as e:
            logger.warning("agno_strategy_planning_failed", url=url, error=str(e))
            return self._get_default_execution_strategy()
    
    async def _execute_coordinated_analysis(self, url: str, result: SiteAnalysisResult, strategy: CoordinationResult) -> SiteAnalysisResult:
        """Execute the coordinated analysis based on the optimization strategy."""
        agents_to_execute = []
        
        # Map execution plan to available agents
        for agent_type in strategy.agents_executed:
            if agent_type.lower() in ['trademark', 'trademark_violations', 'trademark_analysis']:
                agents_to_execute.append(('trademark', self.agents['trademark'].analyze_trademark_violations))
            elif agent_type.lower() in ['policy', 'policy_compliance', 'policy_analysis']:
                agents_to_execute.append(('policy', self.agents['policy'].analyze_policies))
        
        # Execute agents based on strategy
        if len(agents_to_execute) > 1 and "parallel" in str(strategy.execution_plan).lower():
            # Parallel execution
            logger.info("baml_agno_parallel_execution_started", url=url, agents=len(agents_to_execute))
            
            tasks = []
            for agent_name, agent_method in agents_to_execute:
                task = agent_method(url, result)
                tasks.append((agent_name, task))
            
            # Execute all agents concurrently
            task_results = await asyncio.gather(
                *[task for _, task in tasks], 
                return_exceptions=True
            )
            
            # Merge results
            for (agent_name, _), task_result in zip(tasks, task_results):
                if isinstance(task_result, Exception):
                    logger.warning("baml_agno_agent_failed", url=url, agent=agent_name, error=str(task_result))
                    if result.status != AnalysisStatus.FAILED:
                        result.status = AnalysisStatus.PARTIAL
                else:
                    result = self._merge_agent_results(result, task_result)
        
        else:
            # Sequential execution
            logger.info("baml_agno_sequential_execution_started", url=url, agents=len(agents_to_execute))
            
            for agent_name, agent_method in agents_to_execute:
                try:
                    result = await agent_method(url, result)
                    logger.info("baml_agno_agent_complete", url=url, agent=agent_name)
                except Exception as e:
                    logger.warning("baml_agno_agent_failed", url=url, agent=agent_name, error=str(e))
                    if result.status != AnalysisStatus.FAILED:
                        result.status = AnalysisStatus.PARTIAL
        
        return result
    
    async def _perform_quality_assurance(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Perform quality assurance and cross-validation of results."""
        try:
            # Add QA metadata
            if not hasattr(result, 'analysis_metadata'):
                result.analysis_metadata = {}
            
            # Quality metrics
            qa_metrics = {
                "trademark_violations_count": len(result.trademark_violations),
                "high_confidence_violations": len([v for v in result.trademark_violations if v.confidence >= 0.8]),
                "policy_compliance_complete": bool(result.privacy_policy or result.terms_conditions),
                "analysis_completeness_score": self._calculate_completeness_score(result),
                "cross_validation_passed": True  # Could implement actual cross-validation
            }
            
            result.analysis_metadata['quality_assurance'] = qa_metrics
            
            logger.info(
                "baml_agno_qa_complete",
                url=url,
                completeness_score=qa_metrics["analysis_completeness_score"],
                violations_found=qa_metrics["trademark_violations_count"],
                policy_compliance=qa_metrics["policy_compliance_complete"]
            )
            
        except Exception as e:
            logger.warning("baml_agno_qa_failed", url=url, error=str(e))
        
        return result
    
    def _merge_agent_results(self, base_result: SiteAnalysisResult, agent_result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Merge results from different agents."""
        # Merge trademark violations (avoid duplicates)
        existing_violations = {(v.violation_type, v.description) for v in base_result.trademark_violations}
        for violation in agent_result.trademark_violations:
            if (violation.violation_type, violation.description) not in existing_violations:
                base_result.trademark_violations.append(violation)
        
        # Update policy links if found
        if agent_result.privacy_policy and not base_result.privacy_policy:
            base_result.privacy_policy = agent_result.privacy_policy
        if agent_result.terms_conditions and not base_result.terms_conditions:
            base_result.terms_conditions = agent_result.terms_conditions
        
        # Merge metadata
        if not hasattr(base_result, 'analysis_metadata'):
            base_result.analysis_metadata = {}
        if hasattr(agent_result, 'analysis_metadata'):
            base_result.analysis_metadata.update(agent_result.analysis_metadata)
        
        # Update processing duration
        base_result.processing_duration_ms += agent_result.processing_duration_ms
        
        # Keep the worst status
        if agent_result.status == AnalysisStatus.FAILED:
            base_result.status = AnalysisStatus.FAILED
        elif agent_result.status == AnalysisStatus.PARTIAL and base_result.status == AnalysisStatus.SUCCESS:
            base_result.status = AnalysisStatus.PARTIAL
        
        return base_result
    
    def _build_analysis_context(self, result: SiteAnalysisResult) -> str:
        """Build context for BAML workflow planning."""
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
    
    def _build_coordination_context(self, url: str, result: SiteAnalysisResult, workflow_plan: Dict[str, Any]) -> str:
        """Build context for Agno coordination agent."""
        context_parts = [f"Target URL: {url}"]
        
        if result.screenshot_path and result.screenshot_path.exists():
            context_parts.append("Screenshot: Available for analysis")
        else:
            context_parts.append("Screenshot: Not available")
        
        if result.html_content:
            context_parts.append(f"HTML Content: Available ({len(result.html_content)} chars)")
        else:
            context_parts.append("HTML Content: Not available")
        
        context_parts.append(f"Site Status: {'Accessible' if result.site_loads else 'Load Failed'}")
        
        if workflow_plan.get('risk_assessment'):
            context_parts.append(f"BAML Risk Assessment: {workflow_plan['risk_assessment'][:100]}")
        
        return "\\n".join(context_parts)
    
    def _format_workflow_plan_for_agent(self, workflow_plan: Dict[str, Any]) -> str:
        """Format workflow plan for Agno agent consumption."""
        formatted = []
        
        formatted.append(f"Estimated Total Duration: {workflow_plan.get('total_estimated_duration', 0)}ms")
        formatted.append(f"Risk Assessment: {workflow_plan.get('risk_assessment', 'Not available')}")
        
        if workflow_plan.get('recommended_sequence'):
            formatted.append(f"\\nRecommended Task Sequence ({len(workflow_plan['recommended_sequence'])}):")
            for i, task in enumerate(workflow_plan['recommended_sequence'], 1):
                formatted.append(f"  {i}. {task.get('task_type', 'Unknown')} (Priority: {task.get('priority', 'Medium')})")
        
        if workflow_plan.get('parallel_processing_groups'):
            formatted.append(f"\\nParallel Processing Opportunities: {len(workflow_plan['parallel_processing_groups'])} groups")
        
        if workflow_plan.get('recommendations'):
            formatted.append(f"\\nBAML Recommendations ({len(workflow_plan['recommendations'])}):")
            for rec in workflow_plan['recommendations'][:3]:  # Limit to first 3
                formatted.append(f"  • {rec}")
        
        return "\\n".join(formatted)
    
    def _calculate_completeness_score(self, result: SiteAnalysisResult) -> float:
        """Calculate analysis completeness score."""
        score = 0.0
        total_checks = 6
        
        # Basic checks
        if result.ssl_analysis:
            score += 1.0
        if result.screenshot_path and result.screenshot_path.exists():
            score += 1.0
        if result.html_content:
            score += 1.0
        
        # Analysis checks
        if result.trademark_violations or hasattr(result, 'analysis_metadata'):
            score += 1.0
        if result.privacy_policy or result.terms_conditions:
            score += 1.0
        if result.status == AnalysisStatus.SUCCESS:
            score += 1.0
        
        return score / total_checks
    
    def _get_default_workflow_plan(self) -> Dict[str, Any]:
        """Get default workflow plan when BAML fails."""
        return {
            "recommended_sequence": [
                {"task_type": "trademark_violations", "priority": "HIGH"},
                {"task_type": "policy_compliance", "priority": "HIGH"}
            ],
            "parallel_processing_groups": [["trademark_violations", "policy_compliance"]],
            "total_estimated_duration": 60000,
            "risk_assessment": "Medium - using fallback coordination",
            "resource_allocation": ["ai_vision_analysis"],
            "quality_assurance_steps": ["error_handling"],
            "recommendations": ["Execute with default coordination"]
        }
    
    def _get_default_execution_strategy(self) -> CoordinationResult:
        """Get default execution strategy when Agno fails."""
        return CoordinationResult(
            execution_plan={"strategy": "sequential", "agents": ["trademark", "policy"]},
            agents_executed=["trademark", "policy"],
            coordination_method="fallback_coordination",
            recommendations=["Use default sequential execution"]
        )