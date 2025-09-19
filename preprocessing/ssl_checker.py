#!/usr/bin/env python3
"""
SSL Certificate Checker

Validates SSL certificates, checks expiry dates, and provides certificate information.
"""

import asyncio
import socket
import ssl
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import structlog

from .models import SSLInfo

logger = structlog.get_logger()

__all__ = ['SSLChecker']


class SSLChecker:
    """SSL Certificate validation and analysis."""
    
    @staticmethod
    async def check_certificate(url: str) -> SSLInfo:
        """
        Check SSL certificate information for a URL.
        
        Args:
            url: The URL to check (must be HTTPS for meaningful results)
            
        Returns:
            SSLInfo object with certificate details and validation status
        """
        parsed_url = urlparse(url)
        
        # If not HTTPS, return basic info
        if parsed_url.scheme != 'https':
            return SSLInfo(
                has_ssl=False,
                is_valid=False,
                certificate_error="Not using HTTPS"
            )
        
        hostname = parsed_url.hostname
        port = parsed_url.port or 443
        
        if not hostname:
            return SSLInfo(
                has_ssl=False,
                is_valid=False,
                certificate_error="Invalid hostname"
            )
        
        try:
            # Create SSL context
            context = ssl.create_default_context()
            
            # Connect and get certificate
            loop = asyncio.get_event_loop()
            
            def get_certificate():
                with socket.create_connection((hostname, port), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        return ssock.getpeercert()
            
            # Run in thread pool to avoid blocking
            cert = await loop.run_in_executor(None, get_certificate)
            
            if not cert:
                return SSLInfo(
                    has_ssl=True,
                    is_valid=False,
                    certificate_error="Could not retrieve certificate"
                )
            
            # Parse certificate information
            subject = dict(x[0] for x in cert.get('subject', []))
            issuer = dict(x[0] for x in cert.get('issuer', []))
            
            # Parse expiry date
            expires_str = cert.get('notAfter')
            expires_date = None
            days_until_expiry = None
            
            if expires_str:
                try:
                    # Parse certificate date format: 'Jan  1 00:00:00 2025 GMT'  
                    # strptime with %Z often creates naive datetimes, so parse without %Z first
                    if expires_str.endswith(' GMT'):
                        # Remove GMT suffix and parse as naive, then add UTC timezone
                        date_part = expires_str[:-4]  # Remove ' GMT'
                        expires_dt = datetime.strptime(date_part, '%b %d %H:%M:%S %Y')
                        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                    else:
                        # Fallback to original parsing
                        expires_dt = datetime.strptime(expires_str, '%b %d %H:%M:%S %Y %Z')
                        if expires_dt.tzinfo is None:
                            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                    
                    expires_date = expires_dt.isoformat()
                    
                    # Calculate days until expiry - ensure both datetimes are timezone-aware
                    now = datetime.now(timezone.utc)
                    days_until_expiry = (expires_dt - now).days
                    
                except ValueError as e:
                    logger.warning("certificate_date_parse_failed", 
                                 hostname=hostname, 
                                 date_string=expires_str,
                                 error=str(e))
            
            return SSLInfo(
                has_ssl=True,
                is_valid=True,
                issuer=issuer.get('organizationName', issuer.get('commonName', 'Unknown')),
                subject=subject.get('commonName', hostname),
                expires_date=expires_date,
                days_until_expiry=days_until_expiry
            )
            
        except ssl.SSLError as e:
            return SSLInfo(
                has_ssl=True,
                is_valid=False,
                certificate_error=f"SSL Error: {str(e)}"
            )
        except socket.timeout:
            return SSLInfo(
                has_ssl=True,
                is_valid=False,
                certificate_error="Connection timeout"
            )
        except Exception as e:
            return SSLInfo(
                has_ssl=True,
                is_valid=False,
                certificate_error=f"Certificate check failed: {str(e)}"
            )
    
    @staticmethod
    def is_certificate_expiring_soon(ssl_info: SSLInfo, days_threshold: int = 30) -> bool:
        """
        Check if certificate is expiring within the specified threshold.
        
        Args:
            ssl_info: SSL information object
            days_threshold: Number of days to consider as "soon" (default: 30)
            
        Returns:
            True if certificate expires within threshold, False otherwise
        """
        if not ssl_info.is_valid or ssl_info.days_until_expiry is None:
            return False
        
        return ssl_info.days_until_expiry <= days_threshold
    
    @staticmethod
    def get_certificate_status(ssl_info: SSLInfo) -> str:
        """
        Get a human-readable status string for the certificate.
        
        Args:
            ssl_info: SSL information object
            
        Returns:
            Status string describing certificate state
        """
        if not ssl_info.has_ssl:
            return "No SSL/HTTPS"
        
        if not ssl_info.is_valid:
            return f"Invalid: {ssl_info.certificate_error}"
        
        if ssl_info.days_until_expiry is not None:
            if ssl_info.days_until_expiry < 0:
                return f"Expired {abs(ssl_info.days_until_expiry)} days ago"
            elif ssl_info.days_until_expiry <= 7:
                return f"Expires in {ssl_info.days_until_expiry} days (CRITICAL)"
            elif ssl_info.days_until_expiry <= 30:
                return f"Expires in {ssl_info.days_until_expiry} days (WARNING)"
            else:
                return f"Valid, expires in {ssl_info.days_until_expiry} days"
        
        return "Valid certificate"