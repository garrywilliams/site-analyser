"""SSL certificate validation processor."""

import ssl
import socket
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional

import httpx
import structlog

from ..models.analysis import SiteAnalysisResult, SSLAnalysis, AnalysisStatus
from .base import BaseProcessor

logger = structlog.get_logger()


class SSLProcessor(BaseProcessor):
    """Processor for SSL certificate validation and HTTPS checking."""
    
    def __init__(self, config):
        super().__init__(config)
        self.version = "1.0.0"
    
    async def process(self, url: str, result: SiteAnalysisResult) -> SiteAnalysisResult:
        """Analyze SSL certificate and HTTPS configuration."""
        start_time = datetime.now()
        
        try:
            parsed_url = urlparse(url)
            is_https = parsed_url.scheme == "https"
            
            if not is_https:
                result.ssl_analysis = SSLAnalysis(
                    is_https=False,
                    ssl_valid=False
                )
                logger.info("ssl_analysis_complete", url=url, is_https=False)
                self._update_processor_version(result)
                return result
            
            # Check SSL certificate details
            ssl_info = await self._get_ssl_info(parsed_url.hostname, parsed_url.port or 443)
            
            # Verify the site actually loads over HTTPS
            site_accessible = await self._verify_https_accessibility(url)
            
            result.ssl_analysis = SSLAnalysis(
                is_https=True,
                ssl_valid=ssl_info["valid"] and site_accessible,
                ssl_expires=ssl_info["expires"],
                ssl_issuer=ssl_info["issuer"]
            )
            
            logger.info(
                "ssl_analysis_complete",
                url=url,
                is_https=True,
                ssl_valid=result.ssl_analysis.ssl_valid,
                ssl_expires=result.ssl_analysis.ssl_expires,
            )
            
        except Exception as e:
            logger.error("ssl_analysis_failed", url=url, error=str(e))
            result.ssl_analysis = SSLAnalysis(
                is_https=url.startswith("https://"),
                ssl_valid=False
            )
            if result.status != AnalysisStatus.FAILED:
                result.status = AnalysisStatus.PARTIAL
        
        finally:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_duration_ms += int(processing_time)
            self._update_processor_version(result)
        
        return result
    
    async def _get_ssl_info(self, hostname: str, port: int) -> dict:
        """Get SSL certificate information."""
        try:
            context = ssl.create_default_context()
            
            with socket.create_connection((hostname, port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    
                    # Parse expiry date
                    expires_str = cert.get('notAfter')
                    expires = None
                    if expires_str:
                        expires = datetime.strptime(expires_str, '%b %d %H:%M:%S %Y %Z')
                    
                    # Get issuer information
                    issuer_info = cert.get('issuer', ())
                    issuer = None
                    for item in issuer_info:
                        if item[0][0] == 'organizationName':
                            issuer = item[0][1]
                            break
                    
                    return {
                        "valid": True,
                        "expires": expires,
                        "issuer": issuer
                    }
        
        except Exception as e:
            logger.warning("ssl_cert_check_failed", hostname=hostname, error=str(e))
            return {"valid": False, "expires": None, "issuer": None}
    
    async def _verify_https_accessibility(self, url: str) -> bool:
        """Verify that the site is accessible over HTTPS."""
        try:
            timeout = self.config.processing_config.request_timeout_seconds
            
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                verify=True,  # Verify SSL certificates
                follow_redirects=True
            ) as client:
                response = await client.head(url)
                return response.status_code < 400
                
        except httpx.RequestError:
            return False
        except Exception:
            return False