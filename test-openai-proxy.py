#!/usr/bin/env python3
"""Test OpenAI-compatible proxy configuration."""

import asyncio
import os
from pathlib import Path

# Add the project to Python path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from site_analyser.models.config import AIConfig
from site_analyser.utils.ai_client import AIClient

async def test_openai_proxy():
    """Test OpenAI-compatible proxy configuration."""
    
    # Test with default OpenAI configuration (should work with original API)
    print("🧪 Testing standard OpenAI configuration...")
    try:
        standard_config = AIConfig(
            provider="openai",
            model="gpt-4o",
            api_key=os.getenv('OPENAI_API_KEY') or "test-key"
        )
        standard_client = AIClient(standard_config)
        print(f"✅ Standard OpenAI client created successfully")
        print(f"   Provider: {standard_config.provider}")
        print(f"   Model: {standard_config.model}")
        print(f"   Base URL: Default (https://api.openai.com/v1)")
    except Exception as e:
        print(f"❌ Standard OpenAI client failed: {e}")
    
    # Test with custom base URL configuration
    print(f"\n🧪 Testing OpenAI-compatible proxy configuration...")
    try:
        proxy_config = AIConfig(
            provider="openai",
            model="gpt-4o",
            api_key=os.getenv('OPENAI_API_KEY') or "your-proxy-api-key",
            base_url="http://localhost:8000/v1",  # Your local proxy
            timeout=60.0
        )
        proxy_client = AIClient(proxy_config)
        print(f"✅ OpenAI-compatible proxy client created successfully")
        print(f"   Provider: {proxy_config.provider}")
        print(f"   Model: {proxy_config.model}")
        print(f"   Base URL: {proxy_config.base_url}")
        print(f"   Timeout: {proxy_config.timeout}s")
    except Exception as e:
        print(f"❌ Proxy client failed: {e}")
    
    print(f"\n📋 Configuration Options:")
    print(f"   1. Command line: --ai-base-url http://localhost:8000/v1")
    print(f"   2. Environment: OPENAI_BASE_URL=http://localhost:8000/v1")
    print(f"   3. Config file: 'base_url': 'http://localhost:8000/v1' in ai_config")
    
    print(f"\n🚀 Example Usage:")
    print(f"   uv run site-analyser analyze \\")
    print(f"     --urls https://example.com \\")
    print(f"     --ai-base-url http://localhost:8000/v1 \\")
    print(f"     --output-dir ./test-proxy-results")

if __name__ == "__main__":
    asyncio.run(test_openai_proxy())