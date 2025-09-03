"""Trademark infringement detection processor."""

import json
import re
from datetime import datetime

import structlog

from ..models.analysis import SiteAnalysisResult, TrademarkViolation, AnalysisStatus
from .base import BaseProcessor
from ..utils.ai_client import AIClient
from ..utils.rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class TrademarkAnalyzerProcessor(BaseProcessor):
    """Processor for detecting UK Government and HMRC trademark infringements."""
    
    def __init__(self, config, rate_limiter: AIRateLimiter = None):
        super().__init__(config)
        self.version = "1.0.0"
        if rate_limiter is None:
            rate_limiter = AIRateLimiter(config.processing_config.ai_request_delay_seconds)
        self.ai_client = AIClient(config.ai_config, rate_limiter)
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze screenshot for trademark infringements."""
        start_time = datetime.now()
        
        try:
            if not result.screenshot_path or not result.screenshot_path.exists():
                logger.warning("trademark_analysis_skipped_no_screenshot", url=url)
                return result
            
            # Analyze for UK Government branding violations
            uk_gov_violations = await self._analyze_uk_government_branding(
                str(result.screenshot_path), url
            )
            
            # Analyze for HMRC branding violations  
            hmrc_violations = await self._analyze_hmrc_branding(
                str(result.screenshot_path), url
            )
            
            # Combine all violations
            result.trademark_violations = uk_gov_violations + hmrc_violations
            
            logger.info(
                "trademark_analysis_complete",
                url=url,
                total_violations=len(result.trademark_violations),
                uk_gov_violations=len(uk_gov_violations),
                hmrc_violations=len(hmrc_violations),
                high_confidence_violations=len([v for v in result.trademark_violations if v.confidence >= 0.8])
            )
            
        except Exception as e:
            logger.error("trademark_analysis_failed", url=url, error=str(e))
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result
    
    async def _analyze_uk_government_branding(self, image_path: str, url: str) -> list[TrademarkViolation]:
        """Analyze for UK Government branding violations."""
        try:
            response = await self.ai_client.analyze_image(
                image_path,
                self.config.trademark_prompts.uk_government_branding
            )
            
            return self._parse_trademark_response(response, "UK_GOVERNMENT", url)
            
        except Exception as e:
            logger.warning("uk_government_analysis_failed", url=url, error=str(e))
            return []
    
    async def _analyze_hmrc_branding(self, image_path: str, url: str) -> list[TrademarkViolation]:
        """Analyze for HMRC branding violations."""
        try:
            response = await self.ai_client.analyze_image(
                image_path,
                self.config.trademark_prompts.hmrc_branding
            )
            
            return self._parse_trademark_response(response, "HMRC", url)
            
        except Exception as e:
            logger.warning("hmrc_analysis_failed", url=url, error=str(e))
            return []
    
    def _parse_trademark_response(
        self, 
        response: str, 
        violation_type_prefix: str, 
        url: str
    ) -> list[TrademarkViolation]:
        """Parse AI response for trademark violations."""
        violations = []
        
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                # Handle different response formats
                violations_data = data.get('violations', [])
                if not violations_data and 'found' in data:
                    # Alternative format where violations are under 'found'
                    violations_data = data.get('found', [])
                
                for violation_data in violations_data:
                    try:
                        # Handle confidence as text or number
                        confidence_raw = violation_data.get('confidence', 0.0)
                        if isinstance(confidence_raw, str):
                            confidence_map = {
                                'low': 0.3,
                                'medium': 0.6, 
                                'high': 0.9
                            }
                            confidence = confidence_map.get(confidence_raw.lower(), 0.3)
                        else:
                            confidence = float(confidence_raw)
                        
                        description = violation_data.get('description', '')
                        
                        # Extract coordinates if available
                        coordinates = None
                        if 'coordinates' in violation_data:
                            coordinates = violation_data['coordinates']
                        elif 'location' in violation_data:
                            coordinates = violation_data['location']
                        
                        # Determine specific violation type
                        violation_type = violation_type_prefix
                        if 'type' in violation_data:
                            violation_type = f"{violation_type_prefix}_{violation_data['type']}"
                        elif 'category' in violation_data:
                            violation_type = f"{violation_type_prefix}_{violation_data['category']}"
                        
                        violations.append(TrademarkViolation(
                            violation_type=violation_type,
                            confidence=confidence,
                            description=description,
                            coordinates=coordinates
                        ))
                        
                    except (KeyError, ValueError, TypeError) as e:
                        logger.warning(
                            "trademark_violation_parse_error",
                            url=url,
                            violation_data=violation_data,
                            error=str(e)
                        )
                        continue
            
            # Also try to parse simple text responses that might indicate violations
            elif any(keyword in response.lower() for keyword in [
                'violation', 'infringement', 'unauthorized', 'government', 'hmrc', 'crown'
            ]):
                # Create a generic violation from text analysis
                violations.append(TrademarkViolation(
                    violation_type=f"{violation_type_prefix}_TEXT_DETECTION",
                    confidence=0.5,  # Lower confidence for text-based detection
                    description=f"Potential violation detected in text analysis: {response[:200]}..."
                ))
                        
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(
                "trademark_response_parse_failed", 
                response=response[:200], 
                error=str(e)
            )
        
        return violations