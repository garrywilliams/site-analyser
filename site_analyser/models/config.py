"""Configuration models."""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, HttpUrl, Field


class AIConfig(BaseModel):
    provider: str = Field(default="openai", description="AI provider: openai or anthropic")
    api_key: Optional[str] = None
    model: str = Field(default="gpt-4o")
    max_tokens: int = Field(default=1000)
    temperature: float = Field(default=0.1)


class TrademarkPrompts(BaseModel):
    uk_government_branding: str = Field(
        default="""Analyze this website screenshot and identify any potential UK Government branding violations. 
Look for:
1. Use of the Crown logo or similar royal symbols
2. "GOV.UK" branding or similar government styling
3. HMRC logos, branding, or official styling
4. Any text claiming government authority or official status
5. Color schemes that mimic official UK government websites (particularly the distinctive blue and white)

Return a JSON response with violations found, confidence scores (0-1), and descriptions."""
    )
    
    hmrc_branding: str = Field(
        default="""Examine this screenshot for potential HMRC (Her Majesty's Revenue and Customs) trademark infringement:
1. HMRC logos or similar designs
2. Official HMRC color schemes and styling
3. Text claiming to be HMRC or official tax authority
4. Forms or pages that look like official HMRC documents
5. Any misleading tax-related official appearance

Provide JSON response with specific violations, confidence levels, and detailed descriptions."""
    )


class PolicyPrompts(BaseModel):
    privacy_policy_detection: str = Field(
        default="""Look at this website screenshot and identify links to privacy policies or privacy statements. 
Look for text like: "Privacy Policy", "Privacy Statement", "Data Protection", "Privacy Notice", etc.
If you find any, provide the visible text and approximate location coordinates if possible.
Return JSON with found links and their properties."""
    )
    
    terms_conditions_detection: str = Field(
        default="""Identify links to terms and conditions, terms of service, or terms of use in this screenshot.
Look for: "Terms and Conditions", "Terms of Service", "Terms of Use", "Legal Terms", etc.
Return JSON with found links and their locations."""
    )


class ProcessingConfig(BaseModel):
    concurrent_requests: int = Field(default=5, ge=1, le=20)
    request_timeout_seconds: int = Field(default=30, ge=5, le=120)
    screenshot_timeout_seconds: int = Field(default=15, ge=5, le=60)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: int = Field(default=2, ge=1, le=30)
    ai_request_delay_seconds: float = Field(default=1.0, ge=0.1, le=10.0, description="Delay between AI API requests to avoid rate limits")


class OutputConfig(BaseModel):
    results_directory: Path = Field(default=Path("./results"))
    screenshots_directory: Path = Field(default=Path("./results/screenshots"))
    json_output_file: Optional[Path] = Field(default=Path("./results/analysis_results.json"))
    keep_html: bool = Field(default=False)
    keep_screenshots: bool = Field(default=True)


class SiteAnalyserConfig(BaseModel):
    urls: list[HttpUrl]
    ai_config: AIConfig = Field(default_factory=AIConfig)
    trademark_prompts: TrademarkPrompts = Field(default_factory=TrademarkPrompts)
    policy_prompts: PolicyPrompts = Field(default_factory=PolicyPrompts)
    processing_config: ProcessingConfig = Field(default_factory=ProcessingConfig)
    output_config: OutputConfig = Field(default_factory=OutputConfig)