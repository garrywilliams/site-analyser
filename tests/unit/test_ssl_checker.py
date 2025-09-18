#!/usr/bin/env python3
"""
Unit tests for SSL certificate checking functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
import ssl
import socket
from datetime import datetime, timezone

from preprocessing.ssl_checker import SSLChecker
from preprocessing.models import SSLInfo


class TestSSLChecker:
    """Test cases for the SSLChecker class."""
    
    def test_non_https_url_returns_no_ssl(self):
        """Test that HTTP URLs return has_ssl=False."""
        # This is a synchronous test since it doesn't actually make network calls
        import asyncio
        
        async def run_test():
            result = await SSLChecker.check_certificate("http://example.com")
            assert result.has_ssl is False
            assert result.is_valid is False
            assert result.certificate_error == "Not using HTTPS"
            assert result.issuer is None
        
        asyncio.run(run_test())
    
    def test_invalid_hostname_returns_error(self):
        """Test that URLs with invalid hostnames return appropriate error."""
        import asyncio
        
        async def run_test():
            result = await SSLChecker.check_certificate("https://")
            assert result.has_ssl is False
            assert result.is_valid is False
            assert result.certificate_error == "Invalid hostname"
        
        asyncio.run(run_test())
    
    @patch('socket.create_connection')
    @patch('ssl.create_default_context')
    def test_successful_certificate_check(self, mock_ssl_context, mock_socket):
        """Test successful SSL certificate retrieval and parsing."""
        import asyncio
        
        # Mock certificate data (based on a typical cert structure)
        mock_cert = {
            'subject': [
                [('countryName', 'US')],
                [('organizationName', 'Example Corp')],
                [('commonName', 'example.com')]
            ],
            'issuer': [
                [('countryName', 'US')],
                [('organizationName', 'DigiCert Inc')],
                [('commonName', 'DigiCert SHA2 Secure Server CA')]
            ],
            'notAfter': 'Jan 15 23:59:59 2026 GMT'  # Certificate expiry format
        }
        
        # Mock the SSL connection chain
        mock_ssl_socket = MagicMock()
        mock_ssl_socket.getpeercert.return_value = mock_cert
        
        mock_context_instance = MagicMock()
        mock_context_instance.wrap_socket.return_value.__enter__.return_value = mock_ssl_socket
        mock_ssl_context.return_value = mock_context_instance
        
        mock_socket_conn = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_socket_conn
        
        async def run_test():
            result = await SSLChecker.check_certificate("https://example.com")
            
            # Verify the result
            assert result.has_ssl is True
            assert result.is_valid is True
            assert result.issuer == "DigiCert Inc"
            assert result.subject == "example.com"
            assert result.expires_date == "2026-01-15T23:59:59+00:00"
            assert result.days_until_expiry is not None
            assert result.certificate_error is None
        
        asyncio.run(run_test())
    
    @patch('socket.create_connection')
    @patch('ssl.create_default_context') 
    def test_ssl_error_handling(self, mock_ssl_context, mock_socket):
        """Test SSL error handling."""
        import asyncio
        
        # Mock SSL error
        mock_ssl_context.side_effect = ssl.SSLError("Certificate verification failed")
        
        async def run_test():
            result = await SSLChecker.check_certificate("https://badssl.example.com")
            
            assert result.has_ssl is True
            assert result.is_valid is False
            assert "SSL Error:" in result.certificate_error
            assert result.issuer is None
        
        asyncio.run(run_test())
    
    @patch('socket.create_connection')
    def test_connection_timeout(self, mock_socket):
        """Test connection timeout handling."""
        import asyncio
        
        # Mock connection timeout
        mock_socket.side_effect = socket.timeout("Connection timed out")
        
        async def run_test():
            result = await SSLChecker.check_certificate("https://timeout.example.com")
            
            assert result.has_ssl is True
            assert result.is_valid is False
            assert result.certificate_error == "Connection timeout"
        
        asyncio.run(run_test())
    
    def test_certificate_expiry_soon(self):
        """Test certificate expiring soon detection."""
        # Test with certificate expiring in 20 days
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True,
            days_until_expiry=20
        )
        
        assert SSLChecker.is_certificate_expiring_soon(ssl_info, days_threshold=30) is True
        assert SSLChecker.is_certificate_expiring_soon(ssl_info, days_threshold=10) is False
    
    def test_certificate_not_expiring_soon(self):
        """Test certificate not expiring soon."""
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True,
            days_until_expiry=60
        )
        
        assert SSLChecker.is_certificate_expiring_soon(ssl_info, days_threshold=30) is False
    
    def test_invalid_certificate_expiry_check(self):
        """Test expiry check with invalid certificate."""
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=False,
            certificate_error="Invalid certificate"
        )
        
        assert SSLChecker.is_certificate_expiring_soon(ssl_info) is False
    
    def test_get_certificate_status_messages(self):
        """Test human-readable status messages."""
        # No SSL
        ssl_info = SSLInfo(has_ssl=False, is_valid=False)
        assert SSLChecker.get_certificate_status(ssl_info) == "No SSL/HTTPS"
        
        # Invalid certificate
        ssl_info = SSLInfo(
            has_ssl=True, 
            is_valid=False, 
            certificate_error="Expired certificate"
        )
        assert "Invalid: Expired certificate" in SSLChecker.get_certificate_status(ssl_info)
        
        # Expired certificate
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True,
            days_until_expiry=-10
        )
        status = SSLChecker.get_certificate_status(ssl_info)
        assert "Expired 10 days ago" in status
        
        # Expiring soon - critical
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True, 
            days_until_expiry=3
        )
        status = SSLChecker.get_certificate_status(ssl_info)
        assert "CRITICAL" in status
        
        # Expiring soon - warning
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True,
            days_until_expiry=20
        )
        status = SSLChecker.get_certificate_status(ssl_info)
        assert "WARNING" in status
        
        # Valid certificate
        ssl_info = SSLInfo(
            has_ssl=True,
            is_valid=True,
            days_until_expiry=90
        )
        status = SSLChecker.get_certificate_status(ssl_info)
        assert "Valid, expires in 90 days" in status


# Fixtures for common test data
@pytest.fixture
def valid_ssl_info():
    """Fixture providing valid SSL info for testing."""
    return SSLInfo(
        has_ssl=True,
        is_valid=True,
        issuer="DigiCert Inc",
        subject="example.com",
        expires_date="2026-01-15T23:59:59+00:00",
        days_until_expiry=120
    )


@pytest.fixture
def invalid_ssl_info():
    """Fixture providing invalid SSL info for testing."""
    return SSLInfo(
        has_ssl=True,
        is_valid=False,
        certificate_error="Certificate verification failed"
    )


@pytest.fixture
def no_ssl_info():
    """Fixture providing no SSL info for testing."""
    return SSLInfo(
        has_ssl=False,
        is_valid=False,
        certificate_error="Not using HTTPS"
    )