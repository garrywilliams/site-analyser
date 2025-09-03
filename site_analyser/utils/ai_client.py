"""AI client for image analysis using OpenAI or Anthropic."""

import asyncio
import base64
import json
import random
from pathlib import Path
from typing import Optional

import httpx
import structlog

from ..models.config import AIConfig
from .rate_limiter import AIRateLimiter

logger = structlog.get_logger()


class AIClient:
    """Client for AI image analysis services."""
    
    def __init__(self, config: AIConfig, rate_limiter: Optional[AIRateLimiter] = None):
        self.config = config
        self.client = None
        self.rate_limiter = rate_limiter or AIRateLimiter(delay_seconds=1.0)
        
        if config.provider.lower() == "openai":
            import openai
            self.client = openai.AsyncOpenAI(api_key=config.api_key)
        elif config.provider.lower() == "anthropic":
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=config.api_key)
        else:
            raise ValueError(f"Unsupported AI provider: {config.provider}")
    
    async def analyze_image(self, image_path: str, prompt: str) -> str:
        """Analyze an image with the given prompt with rate limit handling."""
        max_retries = 5
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Apply rate limiting before making the request
                await self.rate_limiter.acquire()
                
                if self.config.provider.lower() == "openai":
                    return await self._analyze_with_openai(image_path, prompt)
                elif self.config.provider.lower() == "anthropic":
                    return await self._analyze_with_anthropic(image_path, prompt)
                    
            except Exception as e:
                error_str = str(e)
                
                # Check if it's a rate limit error
                if "429" in error_str or "rate_limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        # Extract wait time from error message if available
                        wait_time = self._extract_retry_after(error_str)
                        if wait_time is None:
                            # Exponential backoff with jitter
                            wait_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        
                        logger.warning(
                            "rate_limit_hit_retrying",
                            image_path=image_path,
                            attempt=attempt + 1,
                            wait_time=wait_time,
                            error=error_str[:200]
                        )
                        
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            "rate_limit_exceeded_max_retries",
                            image_path=image_path,
                            max_retries=max_retries,
                            error=error_str
                        )
                        raise
                else:
                    # Non-rate-limit error, don't retry
                    logger.error("ai_analysis_failed", image_path=image_path, error=error_str)
                    raise
        
        # This shouldn't be reached, but just in case
        raise Exception(f"Failed to analyze image after {max_retries} attempts")
    
    def _extract_retry_after(self, error_message: str) -> Optional[float]:
        """Extract retry-after time from OpenAI error message."""
        try:
            # Look for patterns like "Please try again in 948ms"
            import re
            
            # Pattern for milliseconds
            ms_match = re.search(r'try again in (\d+)ms', error_message)
            if ms_match:
                return float(ms_match.group(1)) / 1000.0
            
            # Pattern for seconds  
            s_match = re.search(r'try again in (\d+)s', error_message)
            if s_match:
                return float(s_match.group(1))
                
            # Pattern for "Retry after X seconds"
            retry_match = re.search(r'retry.after.(\d+)', error_message, re.IGNORECASE)
            if retry_match:
                return float(retry_match.group(1))
                
        except Exception:
            pass
            
        return None
    
    async def _analyze_with_openai(self, image_path: str, prompt: str) -> str:
        """Analyze image using OpenAI GPT-4 Vision."""
        # Encode image as base64
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_data}"}
                        }
                    ]
                }
            ],
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature
        )
        
        return response.choices[0].message.content
    
    async def _analyze_with_anthropic(self, image_path: str, prompt: str) -> str:
        """Analyze image using Anthropic Claude Vision."""
        # Read image as base64
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Determine image type
        image_path_obj = Path(image_path)
        image_type = f"image/{image_path_obj.suffix[1:]}" if image_path_obj.suffix else "image/png"
        
        message = await self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": image_type,
                                "data": image_data
                            }
                        },
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        )
        
        return message.content[0].text if message.content else ""