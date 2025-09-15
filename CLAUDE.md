# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Site Analyser is a comprehensive batch processing pipeline for automated website compliance and trademark monitoring. It's designed to run as a daily Kubernetes job to analyze websites for UK Government and HMRC trademark infringements, privacy policy compliance, and SSL security.

## Development Commands

### Local Development with uv
```bash
# Install dependencies
uv sync --dev

# Install Playwright browsers (standard)
uv run playwright install chromium

# For corporate environments with certificate issues:
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium

# For Linux systems missing dependencies:
uv run playwright install-deps chromium
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium

# Alternative: Use install scripts
./install-playwright-corporate.sh      # Corporate networks
./install-linux-dependencies.sh       # Linux missing libraries

# Or use system Chrome browser (no download required)
export USE_SYSTEM_CHROME=true

# Run the application
uv run site-analyser --urls https://example.com --ai-provider openai

# Run with config file
uv run site-analyser --config example-config.json

# Run with custom OpenAI-compatible proxy
uv run site-analyser --urls https://example.com --ai-base-url http://localhost:8000/v1

# Capture screenshots only (no AI analysis)
uv run site-analyser screenshot --urls https://example.com --output-dir ./screenshots

# Screenshots automatically follow redirects (HTTP → HTTPS)
uv run site-analyser screenshot --urls http://example.com --output-dir ./screenshots --verbose

# Run tests
uv run pytest

# Run type checking
uv run mypy site_analyser

# Format code
uv run black site_analyser tests
uv run ruff check site_analyser tests
```

### Docker Commands
```bash
# Build Docker image
docker build -t site-analyser .

# Run container locally
docker run --env-file .env -v $(pwd)/results:/results site-analyser --urls https://example.com
```

### Kubernetes Deployment
```bash
# Deploy to Kubernetes
kubectl apply -f k8s/

# View job status
kubectl get jobs -n site-analyser
kubectl logs -n site-analyser job/site-analyser-job
```

## Architecture

### Core Components
- **Processors**: Modular analysis components (`processors/`)
  - `SSLProcessor`: HTTPS and SSL certificate validation
  - `WebScraperProcessor`: Screenshot capture and HTML extraction using Playwright
  - `PolicyAnalyzerProcessor`: Privacy policy and terms detection via HTML parsing + AI vision
  - `TrademarkAnalyzerProcessor`: UK Gov/HMRC trademark violation detection using AI vision
- **Models**: Pydantic data models for configuration and results (`models/`)
- **Utils**: AI client abstraction supporting OpenAI and Anthropic (`utils/`)

### Key Features
- Concurrent processing with configurable limits
- Comprehensive error handling and retry logic
- Screenshot-based AI analysis for trademark detection
- HTML parsing for policy link detection with vision fallback
- Structured JSON logging suitable for Kubernetes
- Configurable AI prompts for easy updates
- SSL certificate validation and accessibility checks

### AI Integration
- Supports OpenAI GPT-4 Vision and Anthropic Claude Vision APIs
- Analyzes screenshots for UK Government and HMRC branding violations
- Fallback vision analysis for privacy policy detection when HTML parsing fails
- Configurable prompts in `config.json` or via environment

## Configuration

The system uses Pydantic models for configuration validation. See `example-config.json` for a complete configuration example. Key configuration areas:

- `urls`: List of websites to analyze
- `ai_config`: AI provider settings (OpenAI/Anthropic)
- `processing_config`: Concurrency and timeout settings  
- `output_config`: Results storage configuration
- `trademark_prompts`: Customizable AI prompts for violation detection
- `policy_prompts`: Customizable AI prompts for policy detection

## Environment Variables

Required:
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`: API keys for AI services

Optional:
- `AI_PROVIDER`: Choose between "openai" or "anthropic"
- `AI_MODEL`: Specify AI model to use
- `OPENAI_BASE_URL`: Custom base URL for OpenAI-compatible APIs (e.g., local proxy or alternative service)
- `USE_SYSTEM_CHROME`: Set to 'true' to use system Chrome instead of downloading Playwright browsers (useful for corporate environments)
- `NODE_TLS_REJECT_UNAUTHORIZED`: Set to '0' for corporate environments with self-signed certificates

## Testing

- Unit tests: `tests/unit/` - Test individual processors and models
- Integration tests: `tests/integration/` - Test full pipeline with mocked external services
- Use `pytest -m "not slow"` to skip long-running tests during development