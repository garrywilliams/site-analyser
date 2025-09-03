"""Tests for data models."""

import pytest
from datetime import datetime
from pathlib import Path

from site_analyser.models.analysis import (
    SiteAnalysisResult, 
    SSLAnalysis, 
    PolicyLink, 
    TrademarkViolation,
    AnalysisStatus
)
from site_analyser.models.config import SiteAnalyserConfig, AIConfig


def test_ssl_analysis_model():
    """Test SSL analysis model validation."""
    ssl_analysis = SSLAnalysis(
        is_https=True,
        ssl_valid=True,
        ssl_expires=datetime.now(),
        ssl_issuer="Let's Encrypt"
    )
    
    assert ssl_analysis.is_https is True
    assert ssl_analysis.ssl_valid is True
    assert ssl_analysis.ssl_issuer == "Let's Encrypt"


def test_policy_link_model():
    """Test policy link model validation."""
    policy = PolicyLink(
        text="Privacy Policy",
        url="https://example.com/privacy",
        accessible=True,
        found_method="html_parsing"
    )
    
    assert policy.text == "Privacy Policy"
    assert str(policy.url) == "https://example.com/privacy"
    assert policy.accessible is True


def test_trademark_violation_model():
    """Test trademark violation model."""
    violation = TrademarkViolation(
        violation_type="UK_GOVERNMENT_LOGO",
        confidence=0.85,
        description="Crown logo detected",
        coordinates={"x": 100, "y": 200, "width": 50, "height": 50}
    )
    
    assert violation.violation_type == "UK_GOVERNMENT_LOGO"
    assert violation.confidence == 0.85
    assert violation.coordinates["x"] == 100


def test_site_analysis_result_model():
    """Test main analysis result model."""
    result = SiteAnalysisResult(
        url="https://example.com",
        timestamp=datetime.now(),
        status=AnalysisStatus.SUCCESS,
        site_loads=True,
        processing_duration_ms=1500
    )
    
    assert str(result.url) == "https://example.com"
    assert result.status == AnalysisStatus.SUCCESS
    assert result.processing_duration_ms == 1500


def test_config_validation():
    """Test configuration model validation."""
    config = SiteAnalyserConfig(
        urls=["https://example.com"],
        ai_config=AIConfig(provider="openai", api_key="test-key")
    )
    
    assert len(config.urls) == 1
    assert config.ai_config.provider == "openai"
    assert config.processing_config.concurrent_requests == 5  # default value


def test_invalid_url_validation():
    """Test that invalid URLs are rejected."""
    with pytest.raises(ValueError):
        SiteAnalyserConfig(
            urls=["not-a-valid-url"],
            ai_config=AIConfig(provider="openai")
        )