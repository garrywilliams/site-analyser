"""Rate limiter for AI API requests."""

import asyncio
import time
from typing import Optional

import structlog

logger = structlog.get_logger()


class AIRateLimiter:
    """Rate limiter for AI API requests to prevent 429 errors."""
    
    def __init__(self, delay_seconds: float = 1.0):
        self.delay_seconds = delay_seconds
        self.last_request_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire permission to make an AI API request."""
        async with self._lock:
            if self.last_request_time is not None:
                time_since_last = time.time() - self.last_request_time
                if time_since_last < self.delay_seconds:
                    wait_time = self.delay_seconds - time_since_last
                    logger.debug(
                        "rate_limiter_waiting",
                        wait_time=wait_time,
                        delay_seconds=self.delay_seconds
                    )
                    await asyncio.sleep(wait_time)
            
            self.last_request_time = time.time()
    
    def set_delay(self, delay_seconds: float):
        """Update the delay between requests."""
        self.delay_seconds = delay_seconds
        logger.info("rate_limiter_delay_updated", delay_seconds=delay_seconds)