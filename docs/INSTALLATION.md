# Installation & Setup

Complete guide to installing and configuring Site Analyser.

## Prerequisites

- **Python 3.11+** - Required for modern async features and type hints
- **Git** - For cloning the repository
- **OpenAI API Key** - For GPT-4 Vision analysis (or Anthropic for Claude)

## Installation Methods

### Method 1: UV Package Manager (Recommended)

```bash
# Clone repository
git clone https://github.com/your-org/site-analyser.git
cd site-analyser

# Install with UV (faster than pip)
uv sync

# Install Playwright browsers
playwright install chromium
```

### Method 2: Traditional pip

```bash
# Clone repository
git clone https://github.com/your-org/site-analyser.git
cd site-analyser

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Install Playwright browsers
playwright install chromium
```

### Method 3: Development Setup

```bash
# Clone repository
git clone https://github.com/your-org/site-analyser.git
cd site-analyser

# Install with development dependencies
uv sync --group dev

# Install pre-commit hooks
pre-commit install

# Run tests to verify installation
pytest tests/ -v
```

## Environment Configuration

### 1. Create Environment File

```bash
cp .env.example .env
```

### 2. Configure API Keys

Edit `.env` file:

```env
# Required - Choose one provider
OPENAI_API_KEY=sk-your-openai-key-here
# OR
ANTHROPIC_API_KEY=your-anthropic-key-here

# Configuration (optional)
AI_PROVIDER=openai  # or anthropic
CONCURRENT_REQUESTS=5
AI_REQUEST_DELAY=1.5
```

### 3. API Key Sources

**OpenAI API Key:**
1. Visit [OpenAI API Platform](https://platform.openai.com/api-keys)
2. Create new secret key
3. Copy key to `.env` file

**Anthropic API Key:**
1. Visit [Anthropic Console](https://console.anthropic.com/)
2. Generate new API key
3. Copy key to `.env` file

## Verification

Test your installation:

```bash
# Basic connectivity test
uv run site-analyser --help

# Test with a simple site
uv run site-analyser analyze --urls "https://httpbin.org/get" --output-dir /tmp/test

# Verify results
python analyze_results.py /tmp/test/analysis_results.json
```

## Platform-Specific Notes

### macOS

```bash
# Install dependencies if needed
brew install python@3.11

# Install UV package manager
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Ubuntu/Debian

```bash
# Install Python 3.11
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-pip

# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install system dependencies for Playwright
sudo apt install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libxss1 libasound2
```

### Windows

```powershell
# Install Python 3.11 from python.org or Microsoft Store

# Install UV
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Continue with standard installation
uv sync
playwright install chromium
```

## Docker Installation

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Copy project files
COPY . .

# Install dependencies
RUN uv sync --frozen

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Set environment
ENV PYTHONPATH=/app

CMD ["uv", "run", "site-analyser", "scrape-and-analyze"]
```

## Troubleshooting Installation

### Common Issues

**1. Playwright Browser Installation Fails**
```bash
# Force reinstall browsers
playwright install --force chromium

# On Ubuntu, install system dependencies
sudo apt install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0
```

**2. Permission Errors**
```bash
# On Linux/Mac, ensure correct permissions
chmod +x scripts/*
sudo chown -R $(whoami) ~/.cache/ms-playwright
```

**3. Python Version Issues**
```bash
# Verify Python version
python --version  # Should be 3.11+

# Use specific Python version with UV
uv sync --python python3.11
```

**4. SSL Certificate Issues**
```bash
# Upgrade certificates
pip install --upgrade certifi

# Or disable SSL verification (not recommended for production)
export PYTHONHTTPSVERIFY=0
```

**5. Import Errors**
```bash
# Reinstall with clean cache
uv sync --reinstall

# Verify installation
python -c "from site_analyser.main import cli; print('✅ Installation successful')"
```

### Memory Requirements

- **Minimum**: 2GB RAM
- **Recommended**: 4GB+ RAM for concurrent analysis
- **Storage**: 1GB for dependencies + screenshots

### Network Requirements

- **Outbound HTTPS** (port 443) for AI APIs
- **DNS resolution** for target websites
- **Optional**: Proxy support via environment variables

## Next Steps

After successful installation:

1. **[Configuration](CONFIGURATION.md)** - Customize settings
2. **[CLI Reference](CLI.md)** - Learn command options
3. **[Bot Evasion](BOT_EVASION.md)** - Configure stealth features
4. **Run your first analysis!**

```bash
uv run site-analyser analyze --urls "https://example.com"
```