#!/usr/bin/env python3
"""
Integration tests for the preprocessing module.

Tests the interaction between different components working together.
"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from preprocessing import SiteScraper, ScrapingConfig
from preprocessing.tools import scrape_websites, check_ssl_certificates, load_urls_from_file
from preprocessing.models import SSLInfo, BotProtectionInfo


class TestScraperIntegration:
    """Test SiteScraper with all its components working together."""
    
    @pytest.fixture
    def temp_config(self):
        """Fixture providing a temporary scraping configuration."""
        temp_dir = Path(tempfile.mkdtemp())
        return ScrapingConfig(
            job_id="integration-test",
            output_dir=temp_dir,
            timeout_ms=15000,
            max_concurrent=2
        )
    
    @pytest.mark.asyncio
    async def test_full_scraping_workflow(self, temp_config):
        """Test complete scraping workflow from start to finish."""
        test_urls = ["https://httpbin.org/html", "https://httpbin.org/json"]
        
        async with SiteScraper(temp_config) as scraper:
            # Execute full scraping workflow
            results = await scraper.scrape_urls(test_urls)
            
            # Verify results structure
            assert len(results) == 2
            for result in results:
                assert result.job_id == temp_config.job_id
                assert result.status in ["success", "timeout", "error"]
                assert isinstance(result.ssl_info, SSLInfo)
                assert isinstance(result.bot_protection, BotProtectionInfo)
                assert result.viewport_size == f"{temp_config.viewport_width}x{temp_config.viewport_height}"
            
            # Test JSON saving
            json_path = scraper.save_results_json()
            assert json_path.exists()
            
            # Verify JSON structure
            with open(json_path) as f:
                data = json.load(f)
                assert data['job_id'] == temp_config.job_id
                assert 'timestamp' in data
                assert 'config' in data
                assert 'summary' in data
                assert 'results' in data
                assert len(data['results']) == 2
    
    @pytest.mark.asyncio
    async def test_scraper_with_ssl_analysis(self, temp_config):
        """Test scraper integration with SSL analysis."""
        # Use a known HTTPS site
        test_url = "https://httpbin.org/get"
        
        async with SiteScraper(temp_config) as scraper:
            result = await scraper.scrape_url(test_url)
            
            # Verify SSL integration
            assert result.ssl_info.has_ssl is True
            if result.status == "success":
                # SSL should be analyzed for successful HTTPS requests
                assert result.ssl_info.issuer is not None
                assert result.ssl_info.subject is not None
                # Certificate should be valid for httpbin.org
                assert result.ssl_info.is_valid is True
    
    @pytest.mark.asyncio
    async def test_scraper_with_bot_detection(self, temp_config):
        """Test scraper integration with bot protection detection."""
        # Mock a response that triggers bot protection detection
        test_url = "https://httpbin.org/html"
        
        async with SiteScraper(temp_config) as scraper:
            # Patch the bot detector to simulate protection detection
            with patch('preprocessing.scraper.BotDetector.detect_protection') as mock_detect:
                mock_detect.return_value = BotProtectionInfo(
                    detected=True,
                    protection_type="cloudflare",
                    indicators=["test_indicator"],
                    confidence=0.8
                )
                
                result = await scraper.scrape_url(test_url)
                
                # Verify bot protection integration
                assert result.bot_protection.detected is True
                assert result.bot_protection.protection_type == "cloudflare"
                assert result.bot_protection.confidence == 0.8
    
    @pytest.mark.asyncio
    async def test_scraper_error_handling_integration(self, temp_config):
        """Test scraper error handling with all components."""
        # Use an invalid URL to trigger error handling
        invalid_url = "https://definitely-not-a-real-domain-12345.com"
        
        async with SiteScraper(temp_config) as scraper:
            result = await scraper.scrape_url(invalid_url)
            
            # Should handle errors gracefully
            assert result.status == "error"
            assert result.error_message is not None
            assert result.ssl_info is not None  # Still should have SSL info (failed)
            assert result.bot_protection is not None  # Still should have bot protection info
            assert result.company_name is None
            assert result.html_path is None
            assert result.screenshot_path is None
    
    @pytest.mark.asyncio
    async def test_html_content_management(self, temp_config):
        """Test HTML content is properly saved and loaded."""
        test_url = "https://httpbin.org/html"
        
        async with SiteScraper(temp_config) as scraper:
            result = await scraper.scrape_url(test_url)
            
            if result.status == "success":
                # HTML should be saved to separate file
                assert result.html_path is not None
                assert result.html_size > 0
                
                # HTML file should exist
                html_file_path = temp_config.output_dir / result.html_path
                assert html_file_path.exists()
                
                # Should be able to load HTML content
                loaded_html = scraper.load_html_content(result)
                # Allow small differences in byte counting (encoding, line endings, etc.)
                assert abs(len(loaded_html) - result.html_size) <= 5
                assert "<html>" in loaded_html.lower()
    
    @pytest.mark.asyncio
    async def test_concurrent_processing(self, temp_config):
        """Test concurrent processing with multiple URLs."""
        # Use multiple URLs that should process concurrently
        test_urls = [
            "https://httpbin.org/html",
            "https://httpbin.org/json", 
            "https://httpbin.org/xml"
        ]
        
        async with SiteScraper(temp_config) as scraper:
            import time
            start_time = time.time()
            
            results = await scraper.scrape_urls(test_urls)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Should process concurrently and complete all URLs
            # These are normal HTTP requests, should complete reasonably quickly
            assert duration < 30.0  # Allow generous buffer for network variance
            assert len(results) == 3
            
            # Verify that some processing happened concurrently 
            # by checking that we got results for all URLs
            successful_results = [r for r in results if r.status == "success"]
            assert len(successful_results) > 0  # At least some should succeed


class TestToolsIntegration:
    """Test tool functions integration with underlying components."""
    
    @pytest.mark.asyncio
    async def test_scrape_websites_tool_integration(self):
        """Test scrape_websites tool with all components."""
        test_urls = ["https://httpbin.org/json"]
        
        result = await scrape_websites(
            urls=test_urls,
            job_id="tools-integration-test",
            timeout_ms=15000,
            max_concurrent=1,
            return_html=True
        )
        
        # Verify tool response structure
        assert result['success'] is True
        assert result['job_id'] == "tools-integration-test"
        assert 'summary' in result
        assert 'results' in result
        assert 'output_paths' in result
        
        # Verify individual result structure
        if result['results']:
            site_result = result['results'][0]
            assert 'url' in site_result
            assert 'content' in site_result
            assert 'ssl' in site_result
            assert 'bot_protection' in site_result
            assert 'performance' in site_result
            assert 'status' in site_result
            
            # Verify SSL integration in tool response
            ssl_data = site_result['ssl']
            assert 'has_ssl' in ssl_data
            assert 'is_valid' in ssl_data
            
            # Verify bot protection integration in tool response
            bot_data = site_result['bot_protection']
            assert 'detected' in bot_data
            assert 'confidence' in bot_data
    
    @pytest.mark.asyncio
    async def test_ssl_check_tool_integration(self):
        """Test SSL checking tool integration."""
        test_urls = ["https://httpbin.org", "http://httpbin.org"]
        
        result = await check_ssl_certificates(test_urls)
        
        # Verify tool response
        assert result['success'] is True
        assert len(result['results']) == 2
        assert 'summary' in result
        
        # Check SSL analysis integration
        ssl_summary = result['summary']
        assert 'total' in ssl_summary
        assert 'with_ssl' in ssl_summary
        assert 'valid_ssl' in ssl_summary
        
        # Verify individual SSL results
        https_result = next(r for r in result['results'] if r['url'].startswith('https'))
        http_result = next(r for r in result['results'] if r['url'].startswith('http://'))
        
        assert https_result['ssl']['has_ssl'] is True
        assert http_result['ssl']['has_ssl'] is False
    
    def test_load_urls_from_file_integration(self):
        """Test URL loading tool integration."""
        # Create temporary file with URLs
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("https://example.com\n")
            f.write("# This is a comment\n")
            f.write("https://test.org\n")
            f.write("\n")  # Empty line
            f.write("https://final-url.com\n")
            temp_file_path = f.name
        
        try:
            result = load_urls_from_file(temp_file_path)
            
            # Verify tool response
            assert result['success'] is True
            assert result['count'] == 3  # Should skip comment and empty line
            assert len(result['urls']) == 3
            assert "https://example.com" in result['urls']
            assert "https://test.org" in result['urls'] 
            assert "https://final-url.com" in result['urls']
            assert result['source_file'] == str(Path(temp_file_path).absolute())
            
        finally:
            # Cleanup
            Path(temp_file_path).unlink()
    
    @pytest.mark.asyncio
    async def test_tools_error_handling_integration(self):
        """Test tool error handling integration."""
        # Test with invalid URLs
        result = await scrape_websites(
            urls=["not-a-valid-url"],
            job_id="error-test",
            timeout_ms=5000
        )
        
        # Should handle errors gracefully
        assert result['success'] is True  # Tool succeeded even with failed URL
        assert len(result['results']) == 1
        
        # The individual result should show error
        error_result = result['results'][0]
        assert error_result['status']['status'] == "error"
        assert error_result['status']['error_message'] is not None


class TestComponentInteraction:
    """Test interaction between different preprocessing components."""
    
    def test_ssl_checker_with_bot_detector(self):
        """Test SSL checker and bot detector working together."""
        from preprocessing.ssl_checker import SSLChecker
        from preprocessing.bot_detector import BotDetector
        
        # Test data simulating a Cloudflare-protected HTTPS site
        cloudflare_html = """
        <html>
        <head><title>Attention Required! | Cloudflare</title></head>
        <body>
            <h1>Checking your browser before accessing example.com</h1>
            <p>This process is automatic. Your browser will redirect to your requested content shortly.</p>
            <p>Please allow up to 5 seconds...</p>
            <p>DDoS protection by Cloudflare</p>
        </body>
        </html>
        """
        
        # Both components should work independently
        bot_result = BotDetector.detect_protection(cloudflare_html)
        assert bot_result.detected is True
        assert bot_result.protection_type == "cloudflare"
        
        # SSL checker should work regardless of bot protection
        # (This would normally be tested with actual SSL, but we can verify the classes exist)
        assert hasattr(SSLChecker, 'check_certificate')
        assert hasattr(BotDetector, 'detect_protection')
    
    def test_content_extractor_with_models(self):
        """Test content extractor integration with data models."""
        from preprocessing.content_extractor import ContentExtractor
        from preprocessing.models import ScrapingResult, SSLInfo, BotProtectionInfo
        
        html_content = """
        <html>
        <head>
            <title>Test Company - Official Site</title>
            <meta property="og:site_name" content="Test Company">
        </head>
        <body>
            <h1>Welcome to Test Company</h1>
        </body>
        </html>
        """
        
        # Extract company name
        company_name = ContentExtractor.extract_company_name(html_content, "https://test.com")
        
        # Should integrate properly with ScrapingResult model
        ssl_info = SSLInfo(has_ssl=True, is_valid=True)
        bot_info = BotProtectionInfo(detected=False)
        
        result = ScrapingResult(
            job_id="integration-test",
            original_url="https://test.com",
            final_url="https://test.com",
            domain=ContentExtractor.extract_domain("https://test.com"),
            company_name=company_name,
            html_path="test.html",
            html_size=len(html_content),
            screenshot_path="test.png", 
            screenshot_hash=ContentExtractor.calculate_screenshot_hash(b"test"),
            load_time_ms=1000,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=ssl_info,
            bot_protection=bot_info,
            status="success"
        )
        
        # Verify integration
        assert result.company_name == "Test Company"  # Should prefer og:site_name
        assert result.domain == "test.com"
        assert result.screenshot_hash == ContentExtractor.calculate_screenshot_hash(b"test")
    
    @pytest.mark.asyncio
    async def test_full_pipeline_integration(self):
        """Test the complete preprocessing pipeline integration."""
        # This test simulates the full workflow from configuration to results
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Step 1: Create configuration
            config = ScrapingConfig(
                job_id="pipeline-test",
                output_dir=temp_dir,
                timeout_ms=10000
            )
            
            # Step 2: Use tools layer for processing
            result = await scrape_websites(
                urls=["https://httpbin.org/html"],
                job_id=config.job_id,
                output_dir=str(config.output_dir),
                timeout_ms=config.timeout_ms,
                return_html=False  # Test without HTML to reduce complexity
            )
            
            # Step 3: Verify complete integration
            assert result['success'] is True
            assert result['job_id'] == config.job_id
            
            # Verify output files were created
            output_paths = result['output_paths']
            results_file = Path(output_paths['results_json'])
            assert results_file.exists()
            
            # Verify JSON structure matches our models
            with open(results_file) as f:
                data = json.load(f)
                assert data['job_id'] == config.job_id
                assert 'results' in data
                
                if data['results']:
                    first_result = data['results'][0] 
                    # Should have all expected fields from our models
                    expected_fields = [
                        'job_id', 'original_url', 'final_url', 'domain',
                        'ssl_info', 'bot_protection', 'status', 'timestamp'
                    ]
                    for field in expected_fields:
                        assert field in first_result
        
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir)


class TestAsyncIntegration:
    """Test async/await patterns throughout the system."""
    
    @pytest.mark.asyncio
    async def test_async_context_manager_integration(self):
        """Test async context manager usage."""
        temp_dir = Path(tempfile.mkdtemp())
        config = ScrapingConfig(job_id="async-test", output_dir=temp_dir)
        
        # Test async context manager
        async with SiteScraper(config) as scraper:
            assert scraper.browser is not None
            assert scraper.context is not None
            
            # Perform some async operations
            ssl_info = await scraper.check_ssl_certificate("https://httpbin.org")
            assert isinstance(ssl_info, SSLInfo)
        
        # After context exit, resources should be cleaned up
        # (Browser and context should be closed)
    
    @pytest.mark.asyncio
    async def test_async_batch_processing(self):
        """Test async batch processing integration."""
        temp_dir = Path(tempfile.mkdtemp())
        config = ScrapingConfig(
            job_id="batch-test",
            output_dir=temp_dir,
            max_concurrent=2
        )
        
        urls = [
            "https://httpbin.org/delay/1",
            "https://httpbin.org/delay/1", 
            "https://httpbin.org/delay/1",
            "https://httpbin.org/delay/1"
        ]
        
        async with SiteScraper(config) as scraper:
            import time
            start_time = time.time()
            
            results = await scraper.scrape_urls(urls)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # With max_concurrent=2 and 4 URLs each taking ~1s,
            # should complete in ~2 batches (~2-3 seconds), not 4+ seconds
            assert duration < 6.0  # Allow buffer for network variance
            assert len(results) == 4


# Fixtures for integration tests
@pytest.fixture
def sample_urls():
    """Fixture providing sample URLs for testing."""
    return [
        "https://httpbin.org/html",
        "https://httpbin.org/json",
        "https://httpbin.org/xml"
    ]


@pytest.fixture 
def temp_urls_file():
    """Fixture providing a temporary URLs file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("https://httpbin.org/get\n")
        f.write("# Comment line\n")
        f.write("https://httpbin.org/post\n")
        f.write("\n")  # Empty line
        f.write("https://httpbin.org/put\n")
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def mock_playwright_response():
    """Fixture providing mocked Playwright response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.url = "https://example.com"
    return mock_response