"""Tests for SSL processor."""

import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock

from site_analyser.processors.ssl_checker import SSLProcessor
from site_analyser.models.analysis import SiteAnalysisResult, AnalysisStatus


@pytest.mark.asyncio
async def test_ssl_processor_https_url(sample_config):
    """Test SSL processor with HTTPS URL."""
    processor = SSLProcessor(sample_config)
    
    result = SiteAnalysisResult(
        url="https://example.com",
        timestamp=datetime.now(),
        status=AnalysisStatus.SUCCESS,
        site_loads=True,
        processing_duration_ms=0
    )
    
    with patch.object(processor, '_get_ssl_info') as mock_ssl_info, \
         patch.object(processor, '_verify_https_accessibility') as mock_verify:
        
        mock_ssl_info.return_value = {
            "valid": True,
            "expires": datetime.now(),
            "issuer": "Test CA"
        }
        mock_verify.return_value = True
        
        result = await processor.process("https://example.com", result)
        
        assert result.ssl_analysis is not None
        assert result.ssl_analysis.is_https is True
        assert result.ssl_analysis.ssl_valid is True
        assert result.ssl_analysis.ssl_issuer == "Test CA"


@pytest.mark.asyncio
async def test_ssl_processor_http_url(sample_config):
    """Test SSL processor with HTTP URL."""
    processor = SSLProcessor(sample_config)
    
    result = SiteAnalysisResult(
        url="http://example.com",
        timestamp=datetime.now(),
        status=AnalysisStatus.SUCCESS,
        site_loads=True,
        processing_duration_ms=0
    )
    
    result = await processor.process("http://example.com", result)
    
    assert result.ssl_analysis is not None
    assert result.ssl_analysis.is_https is False
    assert result.ssl_analysis.ssl_valid is False


@pytest.mark.asyncio
async def test_ssl_processor_error_handling(sample_config):
    """Test SSL processor error handling."""
    processor = SSLProcessor(sample_config)
    
    result = SiteAnalysisResult(
        url="https://example.com",
        timestamp=datetime.now(),
        status=AnalysisStatus.SUCCESS,
        site_loads=True,
        processing_duration_ms=0
    )
    
    with patch.object(processor, '_get_ssl_info') as mock_ssl_info:
        mock_ssl_info.side_effect = Exception("SSL check failed")
        
        result = await processor.process("https://example.com", result)
        
        assert result.ssl_analysis is not None
        assert result.ssl_analysis.is_https is True
        assert result.ssl_analysis.ssl_valid is False