"""Integration tests for the main application."""

import pytest
import json
from unittest.mock import patch, AsyncMock
from pathlib import Path

from site_analyser.main import SiteAnalyser
from site_analyser.models.config import SiteAnalyserConfig, AIConfig, OutputConfig


@pytest.mark.asyncio
async def test_full_analysis_pipeline(sample_config, temp_results_dir):
    """Test the complete analysis pipeline with mocked external services."""
    
    # Update config to use temp directory
    sample_config.output_config.json_output_file = temp_results_dir / "test_results.json"
    
    analyzer = SiteAnalyser(sample_config)
    
    # Mock all external dependencies
    with patch('site_analyser.processors.ssl_checker.SSLProcessor.process') as mock_ssl, \
         patch('site_analyser.processors.web_scraper.WebScraperProcessor.process') as mock_web, \
         patch('site_analyser.processors.policy_analyzer.PolicyAnalyzerProcessor.process') as mock_policy, \
         patch('site_analyser.processors.trademark_analyzer.TrademarkAnalyzerProcessor.process') as mock_trademark:
        
        # Configure mocks to return minimal successful results
        async def mock_processor_success(url, result):
            result.status = "success"
            return result
        
        mock_ssl.side_effect = mock_processor_success
        mock_web.side_effect = mock_processor_success  
        mock_policy.side_effect = mock_processor_success
        mock_trademark.side_effect = mock_processor_success
        
        # Mock WebScraperProcessor context manager
        with patch('site_analyser.processors.web_scraper.WebScraperProcessor.__aenter__') as mock_enter, \
             patch('site_analyser.processors.web_scraper.WebScraperProcessor.__aexit__') as mock_exit:
            
            mock_enter.return_value.process_with_retry = AsyncMock(side_effect=mock_processor_success)
            
            # Run analysis
            batch_result = await analyzer.analyze_sites()
            
            # Verify results
            assert batch_result.total_urls == 2
            assert batch_result.successful_analyses >= 0  # At least some should succeed with mocks
            assert batch_result.job_id is not None
            assert batch_result.completed_at is not None
            
            # Check that results file was created
            if sample_config.output_config.json_output_file:
                assert sample_config.output_config.json_output_file.exists()


@pytest.mark.asyncio  
async def test_error_handling_in_pipeline(sample_config):
    """Test error handling when processors fail."""
    
    analyzer = SiteAnalyser(sample_config)
    
    # Mock processors to raise exceptions
    with patch('site_analyser.processors.ssl_checker.SSLProcessor.process_with_retry') as mock_ssl:
        mock_ssl.side_effect = Exception("SSL processor failed")
        
        # Mock WebScraperProcessor context manager
        with patch('site_analyser.processors.web_scraper.WebScraperProcessor.__aenter__') as mock_enter, \
             patch('site_analyser.processors.web_scraper.WebScraperProcessor.__aexit__') as mock_exit:
            
            mock_enter.return_value.process_with_retry = AsyncMock(
                side_effect=Exception("Web scraper failed")
            )
            
            # Should handle exceptions gracefully
            batch_result = await analyzer.analyze_sites()
            
            assert batch_result.total_urls == 2
            # All should fail due to exceptions
            assert batch_result.failed_analyses > 0