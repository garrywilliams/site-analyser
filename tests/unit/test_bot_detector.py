#!/usr/bin/env python3
"""
Unit tests for bot protection detection functionality.
"""

import pytest

from preprocessing.bot_detector import BotDetector
from preprocessing.models import BotProtectionInfo


class TestBotDetector:
    """Test cases for the BotDetector class."""
    
    def test_no_protection_detected(self):
        """Test normal HTML content with no bot protection."""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Normal Website</title></head>
        <body>
            <h1>Welcome to our website</h1>
            <p>This is a completely normal website.</p>
        </body>
        </html>
        """
        
        result = BotDetector.detect_protection(html_content)
        
        assert result.detected is False
        assert result.protection_type is None
        assert result.indicators == []
        assert result.confidence == 0.0
    
    def test_cloudflare_protection_detected(self):
        """Test Cloudflare bot protection detection."""
        html_content = """
        <html>
        <head><title>Checking your browser - Cloudflare</title></head>
        <body>
            <div>
                <h1>Checking your browser before accessing example.com</h1>
                <p>This process is automatic. Your browser will redirect to your requested content shortly.</p>
                <p>Please allow up to 5 seconds...</p>
                <p>DDoS protection by Cloudflare</p>
                <p>Ray ID: 1234567890abcdef</p>
            </div>
        </body>
        </html>
        """
        
        result = BotDetector.detect_protection(html_content)
        
        assert result.detected is True
        assert result.protection_type == "cloudflare"
        assert result.confidence >= 0.7
        assert any("cloudflare" in indicator for indicator in result.indicators)
        assert any("ray_id" in indicator for indicator in result.indicators)
        assert any("checking_your_browser" in indicator for indicator in result.indicators)
    
    def test_recaptcha_protection_detected(self):
        """Test reCAPTCHA bot protection detection."""
        html_content = """
        <html>
        <head><title>Please verify you are human</title></head>
        <body>
            <div id="recaptcha-container">
                <iframe src="https://www.google.com/recaptcha/api2/anchor"></iframe>
                <p>Please verify you are human by completing the reCAPTCHA below.</p>
                <div class="recaptcha-checkbox">I'm not a robot</div>
            </div>
        </body>
        </html>
        """
        
        result = BotDetector.detect_protection(html_content)
        
        assert result.detected is True
        assert result.protection_type == "recaptcha"
        assert result.confidence >= 0.6
        assert any("recaptcha" in indicator for indicator in result.indicators)
    
    def test_ddos_guard_protection_detected(self):
        """Test DDoS Guard bot protection detection."""
        html_content = """
        <html>
        <head><title>DDoS-Guard</title></head>
        <body>
            <div>
                <h1>DDoS-Guard protection active</h1>
                <p>This website is under DDoS attack protection by ddosguard.net</p>
                <p>Please wait while we verify your request...</p>
                <script>
                    // DDoS Guard verification script
                    window.location.href = "https://ddosguard.net/check";
                </script>
            </div>
        </body>
        </html>
        """
        
        result = BotDetector.detect_protection(html_content)
        
        assert result.detected is True
        assert result.protection_type == "ddos_guard"
        assert result.confidence >= 0.7
        assert any("ddos_guard" in indicator for indicator in result.indicators)
    
    def test_rate_limiting_from_error_message(self):
        """Test rate limiting detection from error messages."""
        html_content = "<html><body><h1>Too Many Requests</h1></body></html>"
        error_message = "HTTP 429: Too many requests. Please try again later."
        
        result = BotDetector.detect_protection(html_content, error_message)
        
        assert result.detected is True
        assert result.protection_type == "rate_limit"
        assert result.confidence >= 0.8
        assert any("rate_limit" in indicator for indicator in result.indicators)
        assert any("429" in indicator for indicator in result.indicators)
    
    def test_403_forbidden_error(self):
        """Test 403 Forbidden error detection."""
        error_message = "HTTP 403: Forbidden - Access denied due to suspicious activity"
        
        result = BotDetector.detect_protection("", error_message)
        
        assert result.detected is True
        assert result.protection_type == "unknown"  # Generic protection
        assert any("403" in indicator for indicator in result.indicators)
        assert any("suspicious_activity" in indicator for indicator in result.indicators)
    
    def test_javascript_challenge_detected(self):
        """Test JavaScript challenge detection."""
        html_content = """
        <html>
        <head><title>JavaScript Challenge</title></head>
        <body>
            <div>
                <h1>Please enable JavaScript to continue</h1>
                <p>This site requires JavaScript to verify you are human.</p>
                <script>
                    // JavaScript challenge code
                    var challenge = "verify_human_challenge";
                </script>
            </div>
        </body>
        </html>
        """
        
        result = BotDetector.detect_protection(html_content)
        
        assert result.detected is True
        assert any("javascript_challenge" in indicator for indicator in result.indicators)
    
    def test_meta_refresh_redirect(self):
        """Test meta refresh redirect detection."""
        html_content = '''
        <html>
        <head>
            <title>Redirecting...</title>
            <meta http-equiv="refresh" content="5;url=https://example.com/verified">
        </head>
        <body>
            <p>You will be redirected automatically...</p>
        </body>
        </html>
        '''
        
        result = BotDetector.detect_protection(html_content)
        
        assert any("meta_refresh_redirect" in indicator for indicator in result.indicators)
    
    def test_multiple_indicators_high_confidence(self):
        """Test multiple protection indicators result in high confidence."""
        html_content = """
        <html>
        <head><title>Cloudflare - Checking your browser</title></head>
        <body>
            <div>
                <h1>Attention Required! | Cloudflare</h1>
                <p>Checking your browser before accessing example.com</p>
                <p>This process is automatic. Please allow up to 5 seconds...</p>
                <p>DDoS protection by Cloudflare</p>
                <p>Ray ID: abc123def456</p>
                <script>
                    // Cloudflare challenge script
                    var challenge = true;
                </script>
                <meta http-equiv="refresh" content="5">
            </div>
        </body>
        </html>
        """
        
        result = BotDetector.detect_protection(html_content)
        
        assert result.detected is True
        assert result.protection_type == "cloudflare"
        assert result.confidence >= 0.7
        # Should have multiple indicators
        assert len(result.indicators) >= 4
    
    def test_analyze_html_content_method(self):
        """Test the internal HTML analysis method."""
        html_content = "<html><body><p>Please verify you are human with recaptcha</p></body></html>"
        
        indicators = BotDetector._analyze_html_content(html_content)
        
        assert len(indicators) > 0
        assert any("recaptcha" in indicator for indicator in indicators)
    
    def test_analyze_error_message_method(self):
        """Test the internal error message analysis method."""
        error_message = "HTTP 503 Service Unavailable - Too many automated traffic detected"
        
        indicators = BotDetector._analyze_error_message(error_message)
        
        assert len(indicators) > 0
        assert any("503" in indicator for indicator in indicators)
        assert any("automated_traffic" in indicator for indicator in indicators)
    
    def test_determine_protection_type_method(self):
        """Test the protection type determination logic."""
        # Test Cloudflare indicators
        cloudflare_indicators = ["cloudflare_checking_your_browser", "cloudflare_ray_id"]
        protection_type, confidence = BotDetector._determine_protection_type(cloudflare_indicators)
        
        assert protection_type == "cloudflare"
        assert confidence >= 0.7
        
        # Test rate limit indicators
        rate_limit_indicators = ["http_429_rate_limit", "rate_limit_too_many_requests"]
        protection_type, confidence = BotDetector._determine_protection_type(rate_limit_indicators)
        
        assert protection_type == "rate_limit"
        assert confidence >= 0.8
    
    def test_get_protection_summary(self):
        """Test human-readable protection summary."""
        # No protection
        no_protection = BotProtectionInfo(detected=False)
        summary = BotDetector.get_protection_summary(no_protection)
        assert summary == "No bot protection detected"
        
        # High confidence Cloudflare
        high_confidence = BotProtectionInfo(
            detected=True,
            protection_type="cloudflare",
            confidence=0.9
        )
        summary = BotDetector.get_protection_summary(high_confidence)
        assert "Cloudflare" in summary
        assert "high confidence" in summary.lower()
        
        # Low confidence unknown protection
        low_confidence = BotProtectionInfo(
            detected=True,
            protection_type="unknown",
            confidence=0.3
        )
        summary = BotDetector.get_protection_summary(low_confidence)
        assert "Unknown protection" in summary
        assert "low confidence" in summary.lower()
    
    def test_is_likely_bot_protection(self):
        """Test likelihood determination with different confidence thresholds."""
        # High confidence - should be likely
        high_confidence = BotProtectionInfo(detected=True, confidence=0.8)
        assert BotDetector.is_likely_bot_protection(high_confidence) is True
        assert BotDetector.is_likely_bot_protection(high_confidence, confidence_threshold=0.7) is True
        
        # Medium confidence - depends on threshold
        medium_confidence = BotProtectionInfo(detected=True, confidence=0.4)
        assert BotDetector.is_likely_bot_protection(medium_confidence, confidence_threshold=0.3) is True
        assert BotDetector.is_likely_bot_protection(medium_confidence, confidence_threshold=0.6) is False
        
        # Not detected - should never be likely
        not_detected = BotProtectionInfo(detected=False, confidence=0.9)
        assert BotDetector.is_likely_bot_protection(not_detected) is False
    
    def test_empty_content_and_error(self):
        """Test behavior with empty content and error message."""
        result = BotDetector.detect_protection("", "")
        
        assert result.detected is False
        assert result.protection_type is None
        assert result.indicators == []
        assert result.confidence == 0.0
    
    def test_case_insensitive_detection(self):
        """Test that detection is case insensitive."""
        html_content_upper = "<HTML><BODY><P>CLOUDFLARE CHECKING YOUR BROWSER</P></BODY></HTML>"
        html_content_mixed = "<Html><Body><P>CloudFlare Ray ID: 12345</P></Body></Html>"
        
        result_upper = BotDetector.detect_protection(html_content_upper)
        result_mixed = BotDetector.detect_protection(html_content_mixed)
        
        assert result_upper.detected is True
        assert result_mixed.detected is True
        assert result_upper.protection_type == "cloudflare"
        assert result_mixed.protection_type == "cloudflare"


# Fixtures for common test data
@pytest.fixture
def cloudflare_html():
    """Fixture providing Cloudflare challenge HTML."""
    return """
    <html>
    <head><title>Attention Required! | Cloudflare</title></head>
    <body>
        <div>
            <h1>Checking your browser before accessing example.com</h1>
            <p>This process is automatic. Your browser will redirect to your requested content shortly.</p>
            <p>DDoS protection by Cloudflare</p>
            <p>Ray ID: 1234567890abcdef</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def recaptcha_html():
    """Fixture providing reCAPTCHA challenge HTML."""
    return """
    <html>
    <head><title>Human Verification</title></head>
    <body>
        <div id="recaptcha">
            <p>Please verify you are human</p>
            <iframe src="https://www.google.com/recaptcha/api2/anchor"></iframe>
            <div>I'm not a robot</div>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def rate_limit_error():
    """Fixture providing rate limit error message."""
    return "HTTP 429: Too many requests from your IP. Please try again later."