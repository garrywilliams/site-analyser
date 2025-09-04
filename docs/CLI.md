# CLI Reference

Complete command-line interface reference for Site Analyser.

## Global Options

```bash
uv run site-analyser [GLOBAL_OPTIONS] COMMAND [COMMAND_OPTIONS]
```

### Global Flags

| Flag | Description |
|------|-------------|
| `--debug` | Enable debug logging |
| `--help` | Show help message |

## Commands Overview

| Command | Purpose |
|---------|---------|
| `analyze` | Analyze specific URLs for compliance |
| `scrape-urls` | Extract URLs from HMRC software registry |
| `scrape-and-analyze` | Combined URL extraction and analysis |

---

## `analyze` Command

Analyze websites for compliance and trademark violations.

### Basic Syntax

```bash
uv run site-analyser analyze [OPTIONS]
```

### URL Input Options

```bash
# Single URL
--urls "https://example.com"

# Multiple URLs  
--urls "https://site1.com" --urls "https://site2.com"

# From file (one URL per line)
--urls-file urls.txt

# From JSON configuration
--config config.json
```

### Processing Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--concurrent-requests`, `-j` | int | 5 | Concurrent analysis threads |
| `--ai-delay` | float | 1.5 | Delay between AI requests (seconds) |
| `--ai-provider` | choice | openai | AI provider: `openai` or `anthropic` |

### Bot Evasion Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--stealth` / `--no-stealth` | bool | true | Enable browser fingerprint masking |
| `--random-agents` / `--no-random-agents` | bool | true | Use rotating user agents |
| `--human-behavior` / `--no-human-behavior` | bool | true | Simulate human interactions |
| `--handle-captcha` / `--no-handle-captcha` | bool | true | Attempt CAPTCHA resolution |

### Output Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output-dir`, `-o` | path | ./results | Output directory |
| `--config` | path | - | JSON configuration file |

### Examples

**Basic Analysis:**
```bash
uv run site-analyser analyze --urls "https://example.com"
```

**Batch Analysis with Stealth:**
```bash
uv run site-analyser analyze \
    --urls-file sites.txt \
    --stealth \
    --random-agents \
    --human-behavior \
    --concurrent-requests 1 \
    --ai-delay 3.0 \
    --output-dir compliance-results
```

**High-Speed Analysis (Less Stealth):**
```bash
uv run site-analyser analyze \
    --urls-file sites.txt \
    --no-human-behavior \
    --concurrent-requests 5 \
    --ai-delay 1.0 \
    --output-dir fast-results
```

**Maximum Stealth for Difficult Sites:**
```bash
uv run site-analyser analyze \
    --urls "https://protected-site.com" \
    --stealth \
    --random-agents \
    --human-behavior \
    --handle-captcha \
    --concurrent-requests 1 \
    --ai-delay 5.0 \
    --ai-provider anthropic
```

---

## `scrape-urls` Command

Extract URLs from HMRC software registry.

### Basic Syntax

```bash
uv run site-analyser scrape-urls [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output-file`, `-o` | path | hmrc-urls.txt | Output file for URLs |
| `--max-pages` | int | 50 | Maximum registry pages to scrape |
| `--delay` | float | 1.0 | Delay between page requests |

### Examples

```bash
# Extract all HMRC vendor URLs
uv run site-analyser scrape-urls --output-file vendors.txt

# Limited extraction with delays
uv run site-analyser scrape-urls \
    --output-file vendors.txt \
    --max-pages 10 \
    --delay 2.0
```

---

## `scrape-and-analyze` Command

Combined URL extraction and immediate analysis.

### Basic Syntax

```bash
uv run site-analyser scrape-and-analyze [OPTIONS]
```

### Options

Combines all options from both `scrape-urls` and `analyze` commands.

### Examples

```bash
# Full HMRC vendor analysis
uv run site-analyser scrape-and-analyze \
    --output-dir hmrc-compliance \
    --stealth \
    --random-agents \
    --concurrent-requests 2 \
    --ai-delay 2.5

# Fast analysis with minimal stealth
uv run site-analyser scrape-and-analyze \
    --output-dir hmrc-fast \
    --no-human-behavior \
    --concurrent-requests 5 \
    --max-pages 5
```

---

## Configuration File

Instead of long command lines, use a JSON configuration file:

### config.json
```json
{
  "urls": [
    "https://example.com",
    "https://another-site.com"
  ],
  "ai_config": {
    "provider": "openai",
    "model": "gpt-4o",
    "temperature": 0.1
  },
  "processing_config": {
    "concurrent_requests": 2,
    "ai_request_delay_seconds": 2.5,
    "use_stealth_mode": true,
    "random_user_agents": true,
    "simulate_human_behavior": true,
    "handle_captcha_challenges": true
  },
  "output_config": {
    "results_directory": "./custom-results",
    "screenshots_directory": "./custom-results/screenshots",
    "json_output_file": "./custom-results/analysis.json",
    "keep_screenshots": true,
    "keep_html": false
  }
}
```

### Using Configuration File

```bash
uv run site-analyser analyze --config config.json
```

---

## URL Input Formats

### Text File Format (urls.txt)
```
https://example.com
https://another-site.com  
https://third-site.org
# Comments are ignored
https://final-site.net
```

### Multiple URL Arguments
```bash
uv run site-analyser analyze \
    --urls "https://site1.com" \
    --urls "https://site2.com" \
    --urls "https://site3.com"
```

---

## Environment Variables

Override defaults with environment variables:

```bash
export AI_PROVIDER=anthropic
export CONCURRENT_REQUESTS=3
export AI_REQUEST_DELAY=2.0
export STEALTH_MODE=true

uv run site-analyser analyze --urls-file urls.txt
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Network error |
| 4 | API error |

---

## Performance Tuning

### For Speed
```bash
--no-human-behavior --concurrent-requests 5 --ai-delay 1.0
```

### For Success Rate
```bash
--stealth --random-agents --human-behavior --concurrent-requests 1 --ai-delay 4.0
```

### For Balance
```bash
--stealth --random-agents --no-human-behavior --concurrent-requests 2 --ai-delay 2.5
```

---

## Common Patterns

### Development/Testing
```bash
# Quick test with single site
uv run site-analyser analyze \
    --urls "https://httpbin.org/get" \
    --output-dir /tmp/test

# Debug mode
uv run site-analyser --debug analyze \
    --urls "https://example.com"
```

### Production Analysis
```bash
# Large batch with full compliance
uv run site-analyser analyze \
    --urls-file production-sites.txt \
    --stealth \
    --random-agents \
    --human-behavior \
    --handle-captcha \
    --concurrent-requests 2 \
    --ai-delay 3.0 \
    --output-dir compliance-$(date +%Y%m%d)
```

### HMRC Monitoring
```bash
# Daily HMRC vendor check
uv run site-analyser scrape-and-analyze \
    --output-dir hmrc-$(date +%Y%m%d) \
    --stealth \
    --concurrent-requests 1 \
    --ai-delay 4.0 \
    --max-pages 20
```

---

## Troubleshooting Commands

### Connectivity Test
```bash
uv run site-analyser analyze --urls "https://httpbin.org/get"
```

### API Test  
```bash
uv run site-analyser --debug analyze --urls "https://example.com"
```

### Configuration Validation
```bash
uv run site-analyser analyze --config config.json --urls "https://example.com"
```

### Browser Test
```bash
# Test Playwright installation
playwright-python -c "print('Playwright OK')"
```