#!/usr/bin/env python3
"""
Bot Protection Detector

Analyzes HTML content and error messages to detect various anti-bot protection systems
including Cloudflare, DDoS Guard, reCAPTCHA, rate limiting, and other protection measures.
"""

import re
from typing import List, Optional, Tuple

from .models import BotProtectionInfo

__all__ = ['BotDetector']


class BotDetector:
    """Bot protection detection and analysis."""
    
    # Known bot protection indicators organized by service
    CLOUDFLARE_INDICATORS = [
        "cloudflare", "cf-ray", "cf-mitigated", "checking your browser",
        "ddos protection by cloudflare", "attention required", "ray id:",
    ]
    
    DDOS_GUARD_INDICATORS = [
        "ddos-guard", "checking your browser before accessing",
        "ddosguard.net", "under ddos attack",
    ]
    
    RECAPTCHA_INDICATORS = [
        "recaptcha", "i'm not a robot", "google.com/recaptcha",
        "verify you are human",
    ]
    
    RATE_LIMIT_INDICATORS = [
        "rate limit", "too many requests", "requests per minute",
        "try again later", "temporary block",
    ]
    
    GENERIC_BOT_INDICATORS = [
        "bot protection", "automated traffic", "suspicious activity",
        "access denied", "forbidden", "verification required", "human verification",
    ]
    
    BOT_PROTECTION_ERROR_PHRASES = [
        "access denied", "forbidden", "blocked", "suspicious activity",
        "automated traffic", "bot detected", "rate limit", "too many requests",
        "verification required", "challenge",
    ]
    
    @classmethod
    def detect_protection(cls, html_content: str, error_message: Optional[str] = None) -> BotProtectionInfo:
        """
        Detect bot protection measures based on HTML content and error messages.
        
        Args:
            html_content: The HTML content of the page to analyze
            error_message: Optional error message from failed requests
            
        Returns:
            BotProtectionInfo object with detection results and confidence score
        """
        indicators = []
        
        # Analyze HTML content
        if html_content:
            indicators.extend(cls._analyze_html_content(html_content))
        
        # Analyze error messages
        if error_message:
            indicators.extend(cls._analyze_error_message(error_message))
        
        # Determine protection type and confidence
        if not indicators:
            return BotProtectionInfo(detected=False)
        
        protection_type, confidence = cls._determine_protection_type(indicators)
        detected = confidence > 0.3  # Threshold for detection
        
        return BotProtectionInfo(
            detected=detected,
            protection_type=protection_type,
            indicators=list(set(indicators)),  # Remove duplicates
            confidence=confidence
        )
    
    @classmethod
    def _analyze_html_content(cls, html_content: str) -> List[str]:
        """Analyze HTML content for bot protection indicators."""
        indicators = []
        html_lower = html_content.lower()
        
        # Check for Cloudflare indicators
        for indicator in cls.CLOUDFLARE_INDICATORS:
            if indicator in html_lower:
                indicators.append(f"cloudflare_{indicator.replace(' ', '_')}")
        
        # Check for DDoS Guard indicators  
        for indicator in cls.DDOS_GUARD_INDICATORS:
            if indicator in html_lower:
                indicators.append(f"ddos_guard_{indicator.replace(' ', '_')}")
        
        # Check for reCAPTCHA indicators
        for indicator in cls.RECAPTCHA_INDICATORS:
            if indicator in html_lower:
                indicators.append(f"recaptcha_{indicator.replace(' ', '_')}")
        
        # Check for rate limit indicators
        for indicator in cls.RATE_LIMIT_INDICATORS:
            if indicator in html_lower:
                indicators.append(f"rate_limit_{indicator.replace(' ', '_')}")
        
        # Check for generic bot protection
        for indicator in cls.GENERIC_BOT_INDICATORS:
            if indicator in html_lower:
                indicators.append(f"generic_{indicator.replace(' ', '_')}")
        
        # Check for JavaScript challenges
        if "challenge" in html_lower and ("javascript" in html_lower or "js" in html_lower):
            indicators.append("javascript_challenge")
        
        # Check for meta refresh redirects (common in challenges)
        if re.search(r'<meta[^>]*http-equiv=["\']?refresh["\']?', html_lower):
            indicators.append("meta_refresh_redirect")
        
        return indicators
    
    @classmethod
    def _analyze_error_message(cls, error_message: str) -> List[str]:
        """Analyze error messages for bot protection indicators."""
        indicators = []
        error_lower = error_message.lower()
        
        # HTTP status code indicators
        if "403" in error_message or "forbidden" in error_lower:
            indicators.append("http_403_forbidden")
        if "429" in error_message or "too many requests" in error_lower:
            indicators.append("http_429_rate_limit")
        if "503" in error_message or "service unavailable" in error_lower:
            indicators.append("http_503_service_unavailable")
        
        # Common bot protection error phrases
        for phrase in cls.BOT_PROTECTION_ERROR_PHRASES:
            if phrase in error_lower:
                indicators.append(f"error_message_{phrase.replace(' ', '_')}")
        
        return indicators
    
    @classmethod
    def _determine_protection_type(cls, indicators: List[str]) -> Tuple[Optional[str], float]:
        """
        Determine the type of bot protection and confidence level.
        
        Args:
            indicators: List of detected protection indicators
            
        Returns:
            Tuple of (protection_type, confidence_score)
        """
        # Count indicators by category
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
        
        # Determine protection type with confidence adjustments
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
    
    @classmethod
    def get_protection_summary(cls, bot_info: BotProtectionInfo) -> str:
        """
        Get a human-readable summary of bot protection detection.
        
        Args:
            bot_info: BotProtectionInfo object
            
        Returns:
            Human-readable summary string
        """
        if not bot_info.detected:
            return "No bot protection detected"
        
        confidence_level = "low"
        if bot_info.confidence >= 0.7:
            confidence_level = "high"
        elif bot_info.confidence >= 0.4:
            confidence_level = "medium"
        
        protection_name = bot_info.protection_type or "unknown protection"
        
        return f"{protection_name.title()} protection detected ({confidence_level} confidence: {bot_info.confidence:.2f})"
    
    @classmethod
    def is_likely_bot_protection(cls, bot_info: BotProtectionInfo, confidence_threshold: float = 0.5) -> bool:
        """
        Check if detection indicates likely bot protection.
        
        Args:
            bot_info: BotProtectionInfo object
            confidence_threshold: Minimum confidence for "likely" determination
            
        Returns:
            True if likely bot protection, False otherwise
        """
        return bot_info.detected and bot_info.confidence >= confidence_threshold