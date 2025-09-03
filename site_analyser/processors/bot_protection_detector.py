"""Bot protection detection processor."""

import re
from datetime import datetime
from typing import List, Tuple, Optional

import structlog

from ..models.analysis import SiteAnalysisResult, BotProtectionAnalysis, AnalysisStatus
from .base import BaseProcessor

logger = structlog.get_logger()


class BotProtectionDetectorProcessor(BaseProcessor):
    """Processor for detecting bot protection and anti-automation measures."""
    
    def __init__(self, config):
        super().__init__(config)
        self.version = "1.0.0"
        
        # Known bot protection indicators
        self.cloudflare_indicators = [
            "cloudflare",
            "cf-ray",
            "cf-mitigated",
            "checking your browser",
            "ddos protection by cloudflare",
            "attention required",
            "ray id:",
        ]
        
        self.ddos_guard_indicators = [
            "ddos-guard",
            "checking your browser before accessing",
            "ddosguard.net",
            "under ddos attack",
        ]
        
        self.recaptcha_indicators = [
            "recaptcha",
            "i'm not a robot",
            "google.com/recaptcha",
            "verify you are human",
        ]
        
        self.rate_limit_indicators = [
            "rate limit",
            "too many requests",
            "requests per minute",
            "try again later",
            "temporary block",
        ]
        
        self.generic_bot_indicators = [
            "bot protection",
            "automated traffic",
            "suspicious activity",
            "access denied",
            "forbidden",
            "verification required",
            "human verification",
        ]
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Detect bot protection measures."""
        start_time = datetime.now()
        
        try:
            indicators = []
            protection_type = None
            confidence = 0.0
            detected = False
            
            # Analyze HTTP response
            http_indicators = self._analyze_http_response(result)
            indicators.extend(http_indicators)
            
            # Analyze HTML content if available
            if result.html_content:
                html_indicators = self._analyze_html_content(result.html_content)
                indicators.extend(html_indicators)
            
            # Analyze error messages
            if result.error_message:
                error_indicators = self._analyze_error_message(result.error_message)
                indicators.extend(error_indicators)
            
            # Determine protection type and confidence
            if indicators:
                protection_type, confidence = self._determine_protection_type(indicators)
                detected = confidence > 0.3  # Threshold for detection
            
            result.bot_protection = BotProtectionAnalysis(
                detected=detected,
                protection_type=protection_type,
                indicators=list(set(indicators)),  # Remove duplicates
                confidence=confidence
            )
            
            if detected:
                logger.info(
                    "bot_protection_detected",
                    url=url,
                    protection_type=protection_type,
                    confidence=confidence,
                    indicators=indicators[:3]  # Log first 3 indicators
                )
            else:
                logger.debug("no_bot_protection_detected", url=url)
                
        except Exception as e:
            logger.error("bot_protection_analysis_failed", url=url, error=str(e))
            # Don't fail the whole analysis for this
            result.bot_protection = BotProtectionAnalysis(detected=False)
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result
    
    def _analyze_http_response(self, result: SiteAnalysisResult) -> List[str]:
        """Analyze HTTP response for bot protection indicators."""
        indicators = []
        
        # Check for common HTTP status codes
        if result.error_message:
            error_lower = result.error_message.lower()
            
            # HTTP 403 is often used for bot blocking
            if "403" in result.error_message or "forbidden" in error_lower:
                indicators.append("http_403_forbidden")
            
            # HTTP 429 rate limiting
            if "429" in result.error_message or "too many requests" in error_lower:
                indicators.append("http_429_rate_limit")
            
            # HTTP 503 service unavailable (sometimes used for challenges)
            if "503" in result.error_message or "service unavailable" in error_lower:
                indicators.append("http_503_service_unavailable")
        
        # Check if site doesn't load but SSL is valid (common with bot protection)
        if (not result.site_loads and 
            result.ssl_analysis and 
            result.ssl_analysis.ssl_valid and 
            result.ssl_analysis.is_https):
            indicators.append("valid_ssl_but_blocked_access")
        
        return indicators
    
    def _analyze_html_content(self, html_content: str) -> List[str]:
        """Analyze HTML content for bot protection indicators."""
        indicators = []
        html_lower = html_content.lower()
        
        # Check for Cloudflare indicators
        for indicator in self.cloudflare_indicators:
            if indicator in html_lower:
                indicators.append(f"cloudflare_{indicator.replace(' ', '_')}")
        
        # Check for DDoS Guard indicators
        for indicator in self.ddos_guard_indicators:
            if indicator in html_lower:
                indicators.append(f"ddos_guard_{indicator.replace(' ', '_')}")
        
        # Check for reCAPTCHA indicators
        for indicator in self.recaptcha_indicators:
            if indicator in html_lower:
                indicators.append(f"recaptcha_{indicator.replace(' ', '_')}")
        
        # Check for rate limit indicators
        for indicator in self.rate_limit_indicators:
            if indicator in html_lower:
                indicators.append(f"rate_limit_{indicator.replace(' ', '_')}")
        
        # Check for generic bot protection
        for indicator in self.generic_bot_indicators:
            if indicator in html_lower:
                indicators.append(f"generic_{indicator.replace(' ', '_')}")
        
        # Check for JavaScript challenges
        if "challenge" in html_lower and ("javascript" in html_lower or "js" in html_lower):
            indicators.append("javascript_challenge")
        
        # Check for meta refresh redirects (common in challenges)
        if re.search(r'<meta[^>]*http-equiv=["\']?refresh["\']?', html_lower):
            indicators.append("meta_refresh_redirect")
        
        return indicators
    
    def _analyze_error_message(self, error_message: str) -> List[str]:
        """Analyze error messages for bot protection indicators."""
        indicators = []
        error_lower = error_message.lower()
        
        # Common bot protection error messages
        bot_protection_phrases = [
            "access denied",
            "forbidden",
            "blocked",
            "suspicious activity",
            "automated traffic",
            "bot detected",
            "rate limit",
            "too many requests",
            "verification required",
            "challenge",
        ]
        
        for phrase in bot_protection_phrases:
            if phrase in error_lower:
                indicators.append(f"error_message_{phrase.replace(' ', '_')}")
        
        return indicators
    
    def _determine_protection_type(self, indicators: List[str]) -> Tuple[Optional[str], float]:
        """Determine the type of bot protection and confidence level."""
        cloudflare_score = sum(1 for ind in indicators if "cloudflare" in ind)
        ddos_guard_score = sum(1 for ind in indicators if "ddos_guard" in ind)
        recaptcha_score = sum(1 for ind in indicators if "recaptcha" in ind)
        rate_limit_score = sum(1 for ind in indicators if "rate_limit" in ind or "429" in ind)
        generic_score = sum(1 for ind in indicators if "generic" in ind or "403" in ind or "blocked" in ind)
        
        # Calculate confidence based on number and strength of indicators
        max_score = max(cloudflare_score, ddos_guard_score, recaptcha_score, rate_limit_score, generic_score)
        total_indicators = len(indicators)
        
        # Base confidence on number of indicators and strongest category
        confidence = min((max_score * 0.4) + (total_indicators * 0.1), 1.0)
        
        # Determine protection type
        if cloudflare_score > 0:
            return "cloudflare", max(confidence, 0.7)  # Cloudflare is usually obvious
        elif ddos_guard_score > 0:
            return "ddos_guard", max(confidence, 0.7)
        elif recaptcha_score > 0:
            return "recaptcha", max(confidence, 0.6)
        elif rate_limit_score > 0:
            return "rate_limit", max(confidence, 0.8)  # Rate limits are clear
        elif generic_score > 0:
            return "unknown", max(confidence, 0.4)
        
        return None, confidence