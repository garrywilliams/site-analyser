"""Data models for website analysis results."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, HttpUrl


class AnalysisStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class SSLAnalysis(BaseModel):
    is_https: bool
    ssl_valid: bool
    ssl_expires: Optional[datetime] = None
    ssl_issuer: Optional[str] = None


class PolicyLink(BaseModel):
    text: str
    url: HttpUrl
    accessible: bool
    found_method: str  # "html_parsing" or "vision_analysis"


class TrademarkViolation(BaseModel):
    violation_type: str
    confidence: float
    description: str
    location: Optional[str] = None  # Location where violation was found
    coordinates: Optional[dict] = None  # x, y, width, height if available
    detected_at: Optional[datetime] = None  # When the violation was detected


class BotProtectionAnalysis(BaseModel):
    detected: bool
    protection_type: Optional[str] = None  # "cloudflare", "ddos_guard", "recaptcha", "rate_limit", "unknown"
    indicators: list[str] = []  # List of evidence that suggests bot protection
    confidence: float = 0.0  # 0.0 to 1.0 confidence that this is bot protection


class SiteAnalysisResult(BaseModel):
    url: HttpUrl
    timestamp: datetime
    status: AnalysisStatus
    
    # Core data
    html_content: Optional[str] = None
    screenshot_path: Optional[Path] = None
    
    # SSL Analysis
    ssl_analysis: Optional[SSLAnalysis] = None
    
    # Site functionality
    site_loads: bool
    load_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    
    # Bot protection analysis
    bot_protection: Optional[BotProtectionAnalysis] = None
    
    # Policy analysis
    privacy_policy: Optional[PolicyLink] = None
    terms_conditions: Optional[PolicyLink] = None
    
    # Trademark analysis
    trademark_violations: list[TrademarkViolation] = []
    
    # New compliance analysis fields
    content_relevance: Optional[dict] = None  # Content relevance to tax services
    personal_data_analysis: Optional[dict] = None  # Personal data request detection
    link_functionality: Optional[dict] = None  # Link functionality testing
    website_completeness: Optional[dict] = None  # Website completeness assessment
    language_analysis: Optional[dict] = None  # Language and translation capability
    
    # Processing metadata
    processing_duration_ms: int
    processor_versions: dict[str, str] = {}


class BatchJobResult(BaseModel):
    job_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_urls: int
    successful_analyses: int
    failed_analyses: int
    results: list[SiteAnalysisResult] = []