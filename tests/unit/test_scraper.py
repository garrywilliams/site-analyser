#!/usr/bin/env python3
"""
Unit tests for the main SiteScraper class.

Tests the core scraping logic with mocked dependencies.
"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from preprocessing.scraper import SiteScraper
from preprocessing.models import ScrapingConfig, ScrapingResult, SSLInfo, BotProtectionInfo


class TestSiteScraper:
    """Test cases for the SiteScraper class."""
    
    @pytest.fixture
    def mock_config(self):
        """Fixture providing a mocked scraping configuration."""
        temp_dir = Path(tempfile.mkdtemp())
        return ScrapingConfig(
            job_id="test-job",
            output_dir=temp_dir,
            timeout_ms=10000,
            max_concurrent=2
        )
    
    def test_scraper_initialization(self, mock_config):
        """Test SiteScraper initialization."""
        scraper = SiteScraper(mock_config)
        
        assert scraper.config == mock_config
        assert scraper.browser is None
        assert scraper.context is None
        assert scraper.results == []
    
    @pytest.mark.asyncio
    @patch('preprocessing.scraper.async_playwright')
    async def test_scraper_start(self, mock_playwright, mock_config):
        """Test browser startup."""
        # Mock the Playwright chain with proper async structure
        mock_playwright_instance = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        
        # Mock the async_playwright() call to return an object with start() method
        mock_playwright_obj = AsyncMock()
        mock_playwright_obj.start = AsyncMock(return_value=mock_playwright_instance)
        mock_playwright.return_value = mock_playwright_obj
        
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        
        scraper = SiteScraper(mock_config)
        await scraper.start()
        
        # Verify browser setup
        assert scraper.browser is not None
        assert scraper.context is not None
        mock_browser.new_context.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_scraper_close(self, mock_config):
        """Test browser cleanup."""
        scraper = SiteScraper(mock_config)
        
        # Mock browser and context
        mock_context = AsyncMock()
        mock_browser = AsyncMock()
        scraper.context = mock_context
        scraper.browser = mock_browser
        
        await scraper.close()
        
        # Verify cleanup
        mock_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        assert scraper.context is None
        assert scraper.browser is None
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_config):
        """Test async context manager functionality."""
        with patch.object(SiteScraper, 'start', new=AsyncMock()) as mock_start:
            with patch.object(SiteScraper, 'close', new=AsyncMock()) as mock_close:
                
                async with SiteScraper(mock_config) as scraper:
                    assert isinstance(scraper, SiteScraper)
                
                # Verify start and close were called
                mock_start.assert_called_once()
                mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('preprocessing.scraper.SSLChecker.check_certificate')
    @patch('preprocessing.scraper.BotDetector.detect_protection')
    @patch('preprocessing.scraper.ContentExtractor.extract_company_name')
    @patch('preprocessing.scraper.ContentExtractor.extract_domain')
    @patch('preprocessing.scraper.ContentExtractor.calculate_screenshot_hash')
    async def test_scrape_url_success(self, mock_hash, mock_domain, mock_company, 
                                    mock_bot_detect, mock_ssl_check, mock_config):
        """Test successful URL scraping."""
        # Setup mocks
        mock_ssl_check.return_value = SSLInfo(has_ssl=True, is_valid=True, issuer="Test CA")
        mock_bot_detect.return_value = BotProtectionInfo(detected=False)
        mock_company.return_value = "Test Company"
        mock_domain.return_value = "example.com"
        mock_hash.return_value = "testhash123"
        
        # Mock Playwright components
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response
        mock_page.url = "https://example.com/"
        mock_page.content.return_value = "<html><body>Test content</body></html>"
        mock_page.screenshot.return_value = b"fake_screenshot_data"
        
        scraper = SiteScraper(mock_config)
        scraper.context = mock_context
        
        # Test the scraping
        result = await scraper.scrape_url("https://example.com")
        
        # Verify result
        assert isinstance(result, ScrapingResult)
        assert result.status == "success"
        assert result.original_url == "https://example.com"
        assert result.final_url == "https://example.com/"
        assert result.domain == "example.com"
        assert result.company_name == "Test Company"
        assert result.redirected is True  # URL changed from original
        assert result.ssl_info.has_ssl is True
        assert result.bot_protection.detected is False
        
        # Verify mocks were called
        mock_ssl_check.assert_called_once_with("https://example.com")
        mock_bot_detect.assert_called_once()
        mock_company.assert_called_once()
        mock_page.goto.assert_called_once()
        mock_page.screenshot.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('preprocessing.scraper.SSLChecker.check_certificate')
    @patch('preprocessing.scraper.BotDetector.detect_protection')
    async def test_scrape_url_timeout(self, mock_bot_detect, mock_ssl_check, mock_config):
        """Test URL scraping with timeout."""
        # Setup mocks
        mock_ssl_check.return_value = SSLInfo(has_ssl=True, is_valid=True)
        mock_bot_detect.return_value = BotProtectionInfo(detected=False)
        
        # Mock Playwright timeout
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = asyncio.TimeoutError("Page load timeout")
        
        scraper = SiteScraper(mock_config)
        scraper.context = mock_context
        
        # Test timeout scenario
        result = await scraper.scrape_url("https://slow-site.com")
        
        # Verify timeout handling
        assert result.status == "timeout"
        assert "timeout" in result.error_message.lower()
        assert result.company_name is None
        assert result.html_path is None
        assert result.screenshot_path is None
    
    @pytest.mark.asyncio
    @patch('preprocessing.scraper.SSLChecker.check_certificate')
    @patch('preprocessing.scraper.BotDetector.detect_protection')
    async def test_scrape_url_error(self, mock_bot_detect, mock_ssl_check, mock_config):
        """Test URL scraping with general error."""
        # Setup mocks
        mock_ssl_check.return_value = SSLInfo(has_ssl=False, is_valid=False, certificate_error="Connection failed")
        mock_bot_detect.return_value = BotProtectionInfo(detected=False)
        
        # Mock Playwright error
        mock_page = AsyncMock()
        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page
        mock_page.goto.side_effect = Exception("Network error")
        
        scraper = SiteScraper(mock_config)
        scraper.context = mock_context
        
        # Test error scenario
        result = await scraper.scrape_url("https://broken-site.com")
        
        # Verify error handling
        assert result.status == "error"
        assert result.error_message == "Network error"
        assert result.ssl_info.certificate_error == "Connection failed"
    
    def test_load_html_content_success(self, mock_config):
        """Test successful HTML content loading."""
        scraper = SiteScraper(mock_config)
        
        # Create a test HTML file
        test_html = "<html><body>Test HTML content</body></html>"
        html_file = mock_config.output_dir / "html" / "test.html"
        html_file.parent.mkdir(exist_ok=True)
        html_file.write_text(test_html)
        
        # Create a result object
        result = ScrapingResult(
            job_id="test",
            original_url="https://test.com",
            final_url="https://test.com",
            domain="test.com", 
            company_name="Test",
            html_path="html/test.html",
            html_size=len(test_html),
            screenshot_path="test.png",
            screenshot_hash="hash",
            load_time_ms=1000,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=SSLInfo(has_ssl=True, is_valid=True),
            bot_protection=BotProtectionInfo(detected=False),
            status="success"
        )
        
        # Test loading
        loaded_html = scraper.load_html_content(result)
        assert loaded_html == test_html
    
    def test_load_html_content_missing_file(self, mock_config):
        """Test HTML content loading with missing file."""
        scraper = SiteScraper(mock_config)
        
        # Create result with non-existent file
        result = ScrapingResult(
            job_id="test",
            original_url="https://test.com",
            final_url="https://test.com",
            domain="test.com",
            company_name="Test", 
            html_path="html/nonexistent.html",
            html_size=100,
            screenshot_path="test.png",
            screenshot_hash="hash",
            load_time_ms=1000,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=SSLInfo(has_ssl=True, is_valid=True),
            bot_protection=BotProtectionInfo(detected=False),
            status="success"
        )
        
        # Should return empty string on error
        loaded_html = scraper.load_html_content(result)
        assert loaded_html == ""
    
    def test_load_html_content_no_path(self, mock_config):
        """Test HTML content loading with no path."""
        scraper = SiteScraper(mock_config)
        
        # Create result with no HTML path
        result = ScrapingResult(
            job_id="test",
            original_url="https://test.com",
            final_url="https://test.com", 
            domain="test.com",
            company_name="Test",
            html_path=None,
            html_size=0,
            screenshot_path=None,
            screenshot_hash=None,
            load_time_ms=1000,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=SSLInfo(has_ssl=True, is_valid=True),
            bot_protection=BotProtectionInfo(detected=False),
            status="error"
        )
        
        # Should return empty string
        loaded_html = scraper.load_html_content(result)
        assert loaded_html == ""
    
    @pytest.mark.asyncio
    async def test_scrape_urls_batch(self, mock_config):
        """Test batch URL scraping."""
        scraper = SiteScraper(mock_config)
        
        # Mock scrape_url to return test results
        test_urls = ["https://test1.com", "https://test2.com"]
        mock_results = [
            ScrapingResult(
                job_id="test", original_url=url, final_url=url, domain="test.com",
                company_name="Test", html_path=None, html_size=0, screenshot_path=None,
                screenshot_hash=None, load_time_ms=1000, viewport_size="1920x1080",
                redirected=False, ssl_info=SSLInfo(has_ssl=True, is_valid=True),
                bot_protection=BotProtectionInfo(detected=False), status="success"
            ) for url in test_urls
        ]
        
        with patch.object(scraper, 'scrape_url', side_effect=mock_results) as mock_scrape:
            with patch.object(scraper, 'start', new=AsyncMock()):
                results = await scraper.scrape_urls(test_urls)
        
        # Verify batch processing
        assert len(results) == 2
        assert all(r.status == "success" for r in results)
        assert mock_scrape.call_count == 2
        # Verify results were stored
        assert len(scraper.results) == 2
    
    def test_save_results_json(self, mock_config):
        """Test saving results to JSON file."""
        scraper = SiteScraper(mock_config)
        
        # Add test results
        test_result = ScrapingResult(
            job_id="test-job",
            original_url="https://test.com",
            final_url="https://test.com",
            domain="test.com",
            company_name="Test Company",
            html_path="test.html",
            html_size=100,
            screenshot_path="test.png",
            screenshot_hash="hash123",
            load_time_ms=1500,
            viewport_size="1920x1080",
            redirected=False,
            ssl_info=SSLInfo(has_ssl=True, is_valid=True, issuer="Test CA"),
            bot_protection=BotProtectionInfo(detected=False),
            status="success"
        )
        scraper.results = [test_result]
        
        # Save to JSON
        json_path = scraper.save_results_json()
        
        # Verify file was created
        assert json_path.exists()
        assert json_path.name == "test-job_scraping_results.json"
        
        # Verify JSON content
        with open(json_path) as f:
            data = json.load(f)
        
        assert data["job_id"] == "test-job"
        assert "timestamp" in data
        assert "config" in data
        assert "summary" in data
        assert data["summary"]["total_urls"] == 1
        assert data["summary"]["successful"] == 1
        assert len(data["results"]) == 1
        
        # Verify result structure
        result_data = data["results"][0]
        assert result_data["original_url"] == "https://test.com"
        assert result_data["company_name"] == "Test Company"
        assert result_data["status"] == "success"
    
    def test_load_urls_from_file(self, mock_config):
        """Test loading URLs from file."""
        # Create test file
        urls_file = mock_config.output_dir / "test_urls.txt"
        test_urls = [
            "https://example.com",
            "# This is a comment",
            "https://test.org",
            "",  # Empty line
            "https://final.com"
        ]
        urls_file.write_text("\n".join(test_urls))
        
        # Load URLs
        loaded_urls = SiteScraper.load_urls_from_file(urls_file)
        
        # Should filter out comments and empty lines
        expected_urls = ["https://example.com", "https://test.org", "https://final.com"]
        assert loaded_urls == expected_urls
    
    def test_load_urls_from_file_not_found(self, mock_config):
        """Test loading URLs from non-existent file."""
        non_existent_file = mock_config.output_dir / "missing.txt"
        
        # Should return empty list and not crash
        loaded_urls = SiteScraper.load_urls_from_file(non_existent_file)
        assert loaded_urls == []
    
    def test_url_protocol_handling(self, mock_config):
        """Test URL protocol handling in scrape_url setup."""
        scraper = SiteScraper(mock_config)
        
        # Test that URLs without protocol get HTTPS added
        # This tests the URL preprocessing logic
        test_url = "example.com"
        
        # We can't easily test the full scrape_url without mocking Playwright,
        # but we can test the URL preprocessing logic by checking what URL 
        # would be passed to SSL checker
        with patch('preprocessing.scraper.SSLChecker.check_certificate') as mock_ssl:
            with patch('preprocessing.scraper.BotDetector.detect_protection'):
                with patch.object(scraper, 'context', None):  # Will cause browser error
                    try:
                        asyncio.run(scraper.scrape_url(test_url))
                    except:
                        pass  # Expected to fail without browser
                    
                    # Check that SSL checker was called with HTTPS URL
                    mock_ssl.assert_called_with("https://example.com")


class TestScraperHelperMethods:
    """Test helper methods and utilities."""
    
    @pytest.fixture
    def mock_config(self):
        """Fixture providing a mocked scraping configuration."""
        temp_dir = Path(tempfile.mkdtemp())
        return ScrapingConfig(
            job_id="helper-test",
            output_dir=temp_dir
        )
    
    @pytest.mark.asyncio
    @patch('preprocessing.scraper.SSLChecker.check_certificate')
    async def test_check_ssl_certificate_delegation(self, mock_ssl_check, mock_config):
        """Test that scraper delegates SSL checking correctly."""
        mock_ssl_info = SSLInfo(has_ssl=True, is_valid=True, issuer="Test CA")
        mock_ssl_check.return_value = mock_ssl_info
        
        scraper = SiteScraper(mock_config)
        result = await scraper.check_ssl_certificate("https://example.com")
        
        assert result == mock_ssl_info
        mock_ssl_check.assert_called_once_with("https://example.com")
    
    def test_scraper_config_access(self, mock_config):
        """Test that scraper properly stores and accesses configuration."""
        scraper = SiteScraper(mock_config)
        
        assert scraper.config.job_id == "helper-test"
        assert scraper.config.timeout_ms == 30000  # Default
        assert scraper.config.max_concurrent == 5  # Default
        assert scraper.config.output_dir == mock_config.output_dir


# Fixtures shared across test classes
@pytest.fixture
def sample_scraping_result():
    """Fixture providing a sample scraping result."""
    return ScrapingResult(
        job_id="sample-job",
        original_url="https://example.com",
        final_url="https://example.com/",
        domain="example.com",
        company_name="Example Corp",
        html_path="html/sample.html",
        html_size=1024,
        screenshot_path="screenshots/sample.png",
        screenshot_hash="sample123",
        load_time_ms=1500,
        viewport_size="1920x1080",
        redirected=True,
        ssl_info=SSLInfo(has_ssl=True, is_valid=True, issuer="Sample CA"),
        bot_protection=BotProtectionInfo(detected=False),
        status="success"
    )