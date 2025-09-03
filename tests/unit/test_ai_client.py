"""Tests for AI client."""

import pytest
from unittest.mock import patch, AsyncMock, mock_open
from pathlib import Path

from site_analyser.utils.ai_client import AIClient
from site_analyser.models.config import AIConfig


@pytest.mark.asyncio
async def test_openai_client():
    """Test OpenAI client integration."""
    config = AIConfig(provider="openai", api_key="test-key")
    
    with patch('site_analyser.utils.ai_client.openai.AsyncOpenAI') as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.choices[0].message.content = "Test response"
        mock_client.chat.completions.create.return_value = mock_response
        
        ai_client = AIClient(config)
        
        # Mock file reading
        with patch('builtins.open', mock_open(read_data=b'fake_image_data')):
            result = await ai_client.analyze_image("/path/to/image.png", "Test prompt")
        
        assert result == "Test response"
        mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_anthropic_client():
    """Test Anthropic client integration."""
    config = AIConfig(provider="anthropic", api_key="test-key")
    
    with patch('site_analyser.utils.ai_client.anthropic.AsyncAnthropic') as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        
        # Mock response
        mock_message = AsyncMock()
        mock_message.content = [AsyncMock()]
        mock_message.content[0].text = "Test response"
        mock_client.messages.create.return_value = mock_message
        
        ai_client = AIClient(config)
        
        # Mock file reading
        with patch('builtins.open', mock_open(read_data=b'fake_image_data')):
            result = await ai_client.analyze_image("/path/to/image.png", "Test prompt")
        
        assert result == "Test response"
        mock_client.messages.create.assert_called_once()


def test_invalid_provider():
    """Test invalid AI provider raises error."""
    config = AIConfig(provider="invalid", api_key="test-key")
    
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        AIClient(config)