#!/usr/bin/env python3
"""
Unit tests for HTML content extraction functionality.
"""

import pytest
from unittest.mock import patch

from preprocessing.content_extractor import ContentExtractor


class TestContentExtractor:
    """Test cases for the ContentExtractor class."""
    
    def test_extract_domain_https(self):
        """Test domain extraction from HTTPS URL."""
        url = "https://www.example.com/path/to/page"
        domain = ContentExtractor.extract_domain(url)
        assert domain == "www.example.com"
    
    def test_extract_domain_http(self):
        """Test domain extraction from HTTP URL."""
        url = "http://subdomain.example.org:8080/path"
        domain = ContentExtractor.extract_domain(url)
        assert domain == "subdomain.example.org:8080"
    
    def test_extract_domain_invalid_url(self):
        """Test domain extraction with invalid URL."""
        url = "not-a-valid-url"
        domain = ContentExtractor.extract_domain(url)
        assert domain == ""  # Returns empty string for invalid URL
    
    def test_extract_company_name_from_og_site_name(self):
        """Test company name extraction from OpenGraph site name."""
        html_content = """
        <html>
        <head>
            <meta property="og:site_name" content="Acme Corporation">
            <title>Welcome - Acme Corporation</title>
        </head>
        <body><h1>Welcome</h1></body>
        </html>
        """
        
        company = ContentExtractor.extract_company_name(html_content, "https://example.com")
        assert company == "Acme Corporation"
    
    def test_extract_company_name_from_title(self):
        """Test company name extraction from title tag."""
        html_content = """
        <html>
        <head><title>TechCorp Industries - Home</title></head>
        <body><h1>Welcome</h1></body>
        </html>
        """
        
        company = ContentExtractor.extract_company_name(html_content, "https://example.com")
        assert company == "TechCorp Industries"
    
    def test_extract_company_name_from_h1(self):
        """Test company name extraction from H1 tag."""
        html_content = """
        <html>
        <head></head>
        <body><h1>Global Solutions Ltd</h1></body>
        </html>
        """
        
        company = ContentExtractor.extract_company_name(html_content, "https://example.com")
        assert company == "Global Solutions Ltd"
    
    def test_extract_company_name_title_cleanup(self):
        """Test title cleanup removing common suffixes."""
        html_content = """
        <html>
        <head><title>Best Company | Official Site</title></head>
        <body></body>
        </html>
        """
        
        company = ContentExtractor.extract_company_name(html_content, "https://example.com")
        assert company == "Best Company"
    
    def test_extract_company_name_fallback_to_domain(self):
        """Test fallback to domain when no company name found."""
        html_content = "<html><head></head><body></body></html>"
        
        company = ContentExtractor.extract_company_name(html_content, "https://www.awesome-startup.co.uk")
        assert company == "Awesome-Startup"
    
    def test_extract_company_name_with_parsing_error(self):
        """Test error handling during HTML parsing."""
        # Invalid HTML that might cause parsing issues
        html_content = "<html><head><title>Test</title><unclosed tag>"
        
        with patch('preprocessing.content_extractor.logger') as mock_logger:
            company = ContentExtractor.extract_company_name(html_content, "https://test.com")
            # Should still work and extract from title
            assert company == "Test"
    
    def test_extract_metadata_complete(self):
        """Test complete metadata extraction."""
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Test Page Title</title>
            <meta name="description" content="This is a test page for metadata extraction.">
            <meta name="keywords" content="test, metadata, extraction">
            <meta property="og:title" content="OpenGraph Title">
            <meta property="og:description" content="OpenGraph description text">
            <meta property="og:image" content="https://example.com/image.jpg">
            <link rel="canonical" href="https://example.com/canonical">
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
        </head>
        <body></body>
        </html>
        """
        
        metadata = ContentExtractor.extract_metadata(html_content)
        
        assert metadata['title'] == "Test Page Title"
        assert metadata['description'] == "This is a test page for metadata extraction."
        assert metadata['keywords'] == "test, metadata, extraction"
        assert metadata['og_title'] == "OpenGraph Title"
        assert metadata['og_description'] == "OpenGraph description text"
        assert metadata['og_image'] == "https://example.com/image.jpg"
        assert metadata['canonical_url'] == "https://example.com/canonical"
        assert metadata['language'] == "en"
        assert metadata['charset'] == "UTF-8"
    
    def test_extract_metadata_minimal(self):
        """Test metadata extraction with minimal HTML."""
        html_content = "<html><head><title>Simple Page</title></head><body></body></html>"
        
        metadata = ContentExtractor.extract_metadata(html_content)
        
        assert metadata['title'] == "Simple Page"
        assert metadata['description'] is None
        assert metadata['keywords'] is None
        assert metadata['og_title'] is None
    
    def test_extract_links_basic(self):
        """Test basic link extraction."""
        html_content = """
        <html>
        <body>
            <a href="/internal-page">Internal Link</a>
            <a href="https://external.com" title="External Site">External Link</a>
            <a href="mailto:test@example.com">Email Link</a>
            <a href="">Empty Link</a>
            <a>No href attribute</a>
        </body>
        </html>
        """
        
        links = ContentExtractor.extract_links(html_content, "https://example.com")
        
        # Should find 3 valid links (empty href and no href are filtered)
        assert len(links) == 3
        
        internal_link = next(link for link in links if "internal-page" in link['url'])
        assert internal_link['url'] == "https://example.com/internal-page"
        assert internal_link['text'] == "Internal Link"
        assert internal_link['is_external'] is False
        
        external_link = next(link for link in links if "external.com" in link['url'])
        assert external_link['url'] == "https://external.com"
        assert external_link['title'] == "External Site"
        assert external_link['is_external'] is True
    
    def test_extract_links_relative_urls(self):
        """Test extraction of relative URLs."""
        html_content = """
        <html>
        <body>
            <a href="../parent-page">Parent Directory</a>
            <a href="./same-level">Same Level</a>
            <a href="/absolute-path">Absolute Path</a>
        </body>
        </html>
        """
        
        links = ContentExtractor.extract_links(html_content, "https://example.com/current/page")
        
        assert len(links) == 3
        
        # Check that relative URLs are resolved correctly
        urls = [link['url'] for link in links]
        assert "https://example.com/parent-page" in urls
        assert "https://example.com/current/same-level" in urls
        assert "https://example.com/absolute-path" in urls
    
    def test_calculate_screenshot_hash(self):
        """Test screenshot hash calculation."""
        test_data = b"test screenshot data"
        hash1 = ContentExtractor.calculate_screenshot_hash(test_data)
        hash2 = ContentExtractor.calculate_screenshot_hash(test_data)
        
        # Same data should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64-char hex string
        
        # Different data should produce different hash
        different_data = b"different screenshot data"
        hash3 = ContentExtractor.calculate_screenshot_hash(different_data)
        assert hash1 != hash3
    
    def test_get_content_summary_basic(self):
        """Test basic content summary generation."""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Page</title>
            <link rel="stylesheet" href="styles.css">
            <script src="script.js"></script>
        </head>
        <body>
            <h1>Welcome</h1>
            <p>This is test content.</p>
            <img src="image.jpg" alt="Test image">
            <form action="/submit">
                <input type="text" name="field">
            </form>
        </body>
        </html>
        """
        
        summary = ContentExtractor.get_content_summary(html_content)
        
        assert summary['size_bytes'] == len(html_content)
        assert summary['size_kb'] > 0
        assert summary['line_count'] > 1
        assert summary['has_javascript'] is True
        assert summary['has_css'] is True
        assert summary['has_images'] is True
        assert summary['has_forms'] is True
        assert summary['external_resources'] >= 0
    
    def test_get_content_summary_minimal(self):
        """Test content summary with minimal HTML."""
        html_content = "<html><body><p>Simple content</p></body></html>"
        
        summary = ContentExtractor.get_content_summary(html_content)
        
        assert summary['has_javascript'] is False
        assert summary['has_css'] is False
        assert summary['has_images'] is False
        assert summary['has_forms'] is False
        assert summary['external_resources'] == 0
    
    def test_get_content_summary_external_resources(self):
        """Test external resource counting in content summary."""
        html_content = """
        <html>
        <head>
            <script src="https://cdn.example.com/jquery.js"></script>
            <link rel="stylesheet" href="//fonts.googleapis.com/css">
        </head>
        <body>
            <img src="https://images.example.com/photo.jpg">
        </body>
        </html>
        """
        
        summary = ContentExtractor.get_content_summary(html_content)
        
        # Should detect 3 external resources
        assert summary['external_resources'] == 3
    
    def test_extract_metadata_with_error(self):
        """Test metadata extraction error handling."""
        # Malformed HTML that might cause parsing issues
        html_content = "<html><head><title>Test</title><meta unclosed"
        
        with patch('preprocessing.content_extractor.logger') as mock_logger:
            metadata = ContentExtractor.extract_metadata(html_content)
            # Should return default structure even with parsing errors
            assert isinstance(metadata, dict)
            assert 'title' in metadata
    
    def test_extract_links_with_error(self):
        """Test link extraction error handling."""
        html_content = "<html><body><a href='/test'>Link</a><unclosed"
        base_url = "https://example.com"
        
        with patch('preprocessing.content_extractor.logger') as mock_logger:
            links = ContentExtractor.extract_links(html_content, base_url)
            # Should return empty list on error
            assert isinstance(links, list)
    
    def test_company_name_length_limits(self):
        """Test company name extraction respects length limits."""
        # Very long title that should be rejected
        long_title = "A" * 150  # Longer than 100 char limit
        html_content = f"""
        <html>
        <head><title>{long_title}</title></head>
        <body><h1>Short Name</h1></body>
        </html>
        """
        
        company = ContentExtractor.extract_company_name(html_content, "https://test.com")
        # Should use H1 instead of overly long title
        assert company == "Short Name"
    
    def test_company_name_priority_order(self):
        """Test that company name extraction follows priority order."""
        html_content = """
        <html>
        <head>
            <meta property="og:site_name" content="OpenGraph Name">
            <title>Title Name - Home</title>
        </head>
        <body><h1>H1 Name</h1></body>
        </html>
        """
        
        company = ContentExtractor.extract_company_name(html_content, "https://example.com")
        # Should prefer OpenGraph site name (highest priority)
        assert company == "OpenGraph Name"


# Fixtures for common test data
@pytest.fixture
def sample_html():
    """Fixture providing sample HTML content."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Sample Website</title>
        <meta name="description" content="A sample website for testing">
        <meta property="og:site_name" content="Sample Corp">
    </head>
    <body>
        <h1>Welcome to Sample Corp</h1>
        <p>This is sample content.</p>
        <a href="/about">About Us</a>
        <a href="https://external.com">External Link</a>
    </body>
    </html>
    """


@pytest.fixture
def minimal_html():
    """Fixture providing minimal HTML content."""
    return "<html><head><title>Minimal</title></head><body><p>Content</p></body></html>"


@pytest.fixture
def screenshot_data():
    """Fixture providing test screenshot data."""
    return b"fake screenshot binary data for testing purposes"