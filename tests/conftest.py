"""Pytest configuration and fixtures."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from site_analyser.models.config import SiteAnalyserConfig, AIConfig, ProcessingConfig, OutputConfig


@pytest.fixture
def temp_results_dir(tmp_path):
    """Create a temporary results directory."""
    results_dir = tmp_path / "results"
    screenshots_dir = results_dir / "screenshots" 
    results_dir.mkdir()
    screenshots_dir.mkdir()
    return results_dir


@pytest.fixture
def sample_config(temp_results_dir):
    """Create a sample configuration for testing."""
    return SiteAnalyserConfig(
        urls=["https://example.com", "https://test.com"],
        ai_config=AIConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4-vision-preview"
        ),
        processing_config=ProcessingConfig(
            concurrent_requests=2,
            request_timeout_seconds=10,
            max_retries=1
        ),
        output_config=OutputConfig(
            results_directory=temp_results_dir,
            screenshots_directory=temp_results_dir / "screenshots",
            json_output_file=temp_results_dir / "results.json"
        )
    )


@pytest.fixture
def mock_ai_client():
    """Mock AI client for testing."""
    client = AsyncMock()
    client.analyze_image.return_value = '{"violations": []}'
    return client