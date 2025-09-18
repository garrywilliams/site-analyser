#!/usr/bin/env python3
"""
Unit tests for preprocessing data models and their validation.
"""

import pytest
from datetime import datetime
from pathlib import Path

from preprocessing.models import (
    ScrapingConfig, 
    SSLInfo, 
    BotProtectionInfo, 
    ScrapingResult
)


class TestScrapingConfig:
    """Test cases for the ScrapingConfig dataclass."""
    
    def test_scraping_config_creation(self):
        """Test basic ScrapingConfig creation."""
        config = ScrapingConfig(
            job_id="test-job",
            output_dir=Path("/tmp/test")
        )
        
        assert config.job_id == "test-job"
        assert config.output_dir == Path("/tmp/test")
        # Check defaults
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.timeout_ms == 30000
        assert config.max_concurrent == 5
        assert "Mozilla/5.0" in config.user_agent
    
    def test_scraping_config_custom_values(self):
        """Test ScrapingConfig with custom values."""
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        config = ScrapingConfig(
            job_id="custom-job",
            output_dir=temp_dir / "custom_path",
            viewport_width=1366,
            viewport_height=768,
            timeout_ms=60000,
            max_concurrent=3,
            user_agent="CustomBot/1.0"
        )
        
        assert config.viewport_width == 1366
        assert config.viewport_height == 768
        assert config.timeout_ms == 60000
        assert config.max_concurrent == 3
        assert config.user_agent == "CustomBot/1.0"
    
    def test_scraping_config_output_dir_creation(self):
        """Test that output directory is created on initialization."""
        import tempfile
        import shutil
        
        # Use temporary directory for testing
        temp_dir = Path(tempfile.mkdtemp())
        test_path = temp_dir / "new_directory"
        
        try:
            # Ensure directory doesn't exist initially
            assert not test_path.exists()
            
            config = ScrapingConfig(
                job_id="dir-test",
                output_dir=test_path
            )
            
            # Directory should be created
            assert test_path.exists()
            assert test_path.is_dir()
            assert config.output_dir == test_path
            
        finally:
            # Cleanup
            shutil.rmtree(temp_dir)
    
    def test_scraping_config_path_conversion(self):
        """Test that string paths are converted to Path objects."""
        import tempfile
        temp_dir = tempfile.mkdtemp()
        
        config = ScrapingConfig(
            job_id="path-test",
            output_dir=temp_dir  # Pass as string
        )
        
        # Should be converted to Path object
        assert isinstance(config.output_dir, Path)
        assert str(config.output_dir) == temp_dir


class TestSSLInfo:
    """Test cases for the SSLInfo dataclass."""
    
    def test_ssl_info_basic_creation(self):
        """Test basic SSLInfo creation."""
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True
        )
        
        assert ssl_info.has_ssl is True
        assert ssl_info.is_valid is True
        # Check defaults
        assert ssl_info.issuer is None
        assert ssl_info.subject is None
        assert ssl_info.expires_date is None
        assert ssl_info.days_until_expiry is None
        assert ssl_info.certificate_error is None
    
    def test_ssl_info_complete(self):
        """Test SSLInfo with all fields populated."""
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True,
            issuer="Let's Encrypt Authority X3",
            subject="example.com",
            expires_date="2025-12-31T23:59:59+00:00",
            days_until_expiry=365,
            certificate_error=None
        )
        
        assert ssl_info.issuer == "Let's Encrypt Authority X3"
        assert ssl_info.subject == "example.com"
        assert ssl_info.expires_date == "2025-12-31T23:59:59+00:00"
        assert ssl_info.days_until_expiry == 365
    
    def test_ssl_info_invalid_certificate(self):
        """Test SSLInfo for invalid certificate."""
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=False,
            certificate_error="Certificate verification failed"
        )
        
        assert ssl_info.has_ssl is True
        assert ssl_info.is_valid is False
        assert ssl_info.certificate_error == "Certificate verification failed"
    
    def test_ssl_info_no_ssl(self):
        """Test SSLInfo for HTTP (no SSL)."""
        ssl_info = SSLInfo(
            has_ssl=False,
            is_valid=False,
            certificate_error="Not using HTTPS"
        )
        
        assert ssl_info.has_ssl is False
        assert ssl_info.is_valid is False
        assert ssl_info.certificate_error == "Not using HTTPS"


class TestBotProtectionInfo:
    """Test cases for the BotProtectionInfo dataclass."""
    
    def test_bot_protection_info_no_protection(self):
        """Test BotProtectionInfo for no protection detected."""
        bot_info = BotProtectionInfo(detected=False)
        
        assert bot_info.detected is False
        # Check defaults
        assert bot_info.protection_type is None
        assert bot_info.indicators == []  # Should be set by __post_init__
        assert bot_info.confidence == 0.0
    
    def test_bot_protection_info_with_protection(self):
        """Test BotProtectionInfo with protection detected."""
        indicators = ["cloudflare_checking_your_browser", "cloudflare_ray_id"]
        bot_info = BotProtectionInfo(
            detected=True,
            protection_type="cloudflare",
            indicators=indicators,
            confidence=0.8
        )
        
        assert bot_info.detected is True
        assert bot_info.protection_type == "cloudflare"
        assert bot_info.indicators == indicators
        assert bot_info.confidence == 0.8
    
    def test_bot_protection_info_post_init_indicators(self):
        """Test that __post_init__ sets empty list for indicators."""
        # Test with None indicators (should be set to empty list)
        bot_info = BotProtectionInfo(
            detected=False,
            indicators=None
        )
        
        assert bot_info.indicators == []
        
        # Test with provided indicators (should remain unchanged)
        provided_indicators = ["test_indicator"]
        bot_info2 = BotProtectionInfo(
            detected=True,
            indicators=provided_indicators
        )
        
        assert bot_info2.indicators == provided_indicators
    
    def test_bot_protection_info_rate_limit(self):
        """Test BotProtectionInfo for rate limiting."""
        bot_info = BotProtectionInfo(
            detected=True,
            protection_type="rate_limit",
            indicators=["http_429_rate_limit", "rate_limit_too_many_requests"],
            confidence=0.9
        )
        
        assert bot_info.protection_type == "rate_limit"
        assert bot_info.confidence == 0.9
        assert len(bot_info.indicators) == 2


class TestScrapingResult:
    """Test cases for the ScrapingResult dataclass."""
    
    def test_scraping_result_basic_creation(self):
        """Test basic ScrapingResult creation."""
        ssl_info = SSLInfo(has_ssl=True, is_valid=True)
        bot_info = BotProtectionInfo(detected=False)
        
        result = ScrapingResult(
            job_id="test-job",
            original_url="https://example.com",
            final_url="https://example.com/",
            domain="example.com",
            company_name="Example Corp",
            html_path="html/test.html",
            html_size=1024,
            screenshot_path="screenshots/test.png",
            screenshot_hash="abc123",
            load_time_ms=1500,
            viewport_size="1920x1080",
            redirected=True,
            ssl_info=ssl_info,
            bot_protection=bot_info,
            status="success"
        )
        
        assert result.job_id == "test-job"
        assert result.original_url == "https://example.com"
        assert result.final_url == "https://example.com/"
        assert result.domain == "example.com"
        assert result.company_name == "Example Corp"
        assert result.html_size == 1024
        assert result.load_time_ms == 1500
        assert result.redirected is True
        assert result.status == "success"
        assert result.ssl_info == ssl_info
        assert result.bot_protection == bot_info
    
    def test_scraping_result_error_case(self):
        """Test ScrapingResult for error scenarios."""
        ssl_info = SSLInfo(has_ssl=False, is_valid=False, certificate_error="Connection failed")
        bot_info = BotProtectionInfo(detected=False)
        
        result = ScrapingResult(
            job_id="error-test",
            original_url="https://broken-site.com",
            final_url="https://broken-site.com",
            domain="broken-site.com",
            company_name=None,
            html_path=None,
            html_size=0,
            screenshot_path=None,
            screenshot_hash=None,
            load_time_ms=0,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=ssl_info,
            bot_protection=bot_info,
            status="error",
            error_message="Connection timeout"
        )
        
        assert result.status == "error"
        assert result.error_message == "Connection timeout"
        assert result.company_name is None
        assert result.html_path is None
        assert result.screenshot_path is None
        assert result.html_size == 0
    
    def test_scraping_result_timestamp_auto_generation(self):
        """Test that timestamp is auto-generated if not provided."""
        ssl_info = SSLInfo(has_ssl=True, is_valid=True)
        bot_info = BotProtectionInfo(detected=False)
        
        before_creation = datetime.now()
        
        result = ScrapingResult(
            job_id="timestamp-test",
            original_url="https://example.com",
            final_url="https://example.com",
            domain="example.com",
            company_name="Test Corp",
            html_path="test.html",
            html_size=100,
            screenshot_path="test.png",
            screenshot_hash="hash123",
            load_time_ms=1000,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=ssl_info,
            bot_protection=bot_info,
            status="success"
            # timestamp not provided - should be auto-generated
        )
        
        after_creation = datetime.now()
        
        # Timestamp should be set
        assert result.timestamp is not None
        
        # Parse timestamp and verify it's between before and after
        timestamp_dt = datetime.fromisoformat(result.timestamp)
        assert before_creation <= timestamp_dt <= after_creation
    
    def test_scraping_result_custom_timestamp(self):
        """Test ScrapingResult with custom timestamp."""
        custom_timestamp = "2025-01-01T12:00:00.000000"
        ssl_info = SSLInfo(has_ssl=True, is_valid=True)
        bot_info = BotProtectionInfo(detected=False)
        
        result = ScrapingResult(
            job_id="custom-timestamp-test",
            original_url="https://example.com",
            final_url="https://example.com",
            domain="example.com",
            company_name="Test Corp",
            html_path="test.html",
            html_size=100,
            screenshot_path="test.png",
            screenshot_hash="hash123",
            load_time_ms=1000,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=ssl_info,
            bot_protection=bot_info,
            status="success",
            timestamp=custom_timestamp
        )
        
        assert result.timestamp == custom_timestamp


# Fixtures for common test data
@pytest.fixture
def valid_ssl_info():
    """Fixture providing valid SSL info."""
    return SSLInfo(
        has_ssl=True,
        is_valid=True,
        issuer="Let's Encrypt",
        subject="example.com",
        expires_date="2025-12-31T23:59:59+00:00",
        days_until_expiry=300
    )


@pytest.fixture
def no_protection_bot_info():
    """Fixture providing no bot protection info."""
    return BotProtectionInfo(detected=False)


@pytest.fixture
def cloudflare_bot_info():
    """Fixture providing Cloudflare bot protection info."""
    return BotProtectionInfo(
        detected=True,
        protection_type="cloudflare",
        indicators=["cloudflare_checking_your_browser", "cloudflare_ray_id"],
        confidence=0.8
    )


@pytest.fixture
def sample_config():
    """Fixture providing sample scraping configuration."""
    return ScrapingConfig(
        job_id="sample-job",
        output_dir=Path("/tmp/sample")
    )