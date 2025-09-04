# Configuration Guide

Complete guide to configuring Site Analyser for your specific needs.

## Configuration Methods

Site Analyser can be configured through:

1. **CLI Arguments** - Command line options (highest priority)
2. **Configuration File** - JSON configuration file  
3. **Environment Variables** - System environment variables
4. **Defaults** - Built-in default values (lowest priority)

## CLI Configuration

See [CLI Reference](CLI.md) for all command-line options.

```bash
uv run site-analyser analyze \
    --ai-provider openai \
    --concurrent-requests 2 \
    --ai-delay 2.5 \
    --stealth \
    --output-dir results
```

## Configuration File

### Basic Structure

```json
{
  "urls": ["https://example.com"],
  "ai_config": { ... },
  "processing_config": { ... },
  "output_config": { ... }
}
```

### Complete Example

```json
{
  "urls": [
    "https://example.com",
    "https://another-site.com"
  ],
  
  "ai_config": {
    "provider": "openai",
    "api_key": "sk-your-key-here",
    "model": "gpt-4o", 
    "max_tokens": 1000,
    "temperature": 0.1,
    "enable_reasoning": true,
    "enable_structured_output": true,
    "agent_memory": false
  },
  
  "processing_config": {
    "concurrent_requests": 2,
    "request_timeout_seconds": 30,
    "screenshot_timeout_seconds": 15,
    "max_retries": 3,
    "retry_delay_seconds": 2,
    "ai_request_delay_seconds": 2.5,
    
    "use_stealth_mode": true,
    "random_user_agents": true,
    "simulate_human_behavior": true,
    "handle_captcha_challenges": true
  },
  
  "output_config": {
    "results_directory": "./results",
    "screenshots_directory": "./results/screenshots", 
    "json_output_file": "./results/analysis.json",
    "keep_html": false,
    "keep_screenshots": true
  }
}
```

### Using Configuration File

```bash
uv run site-analyser analyze --config config.json
```

## Environment Variables

Set environment variables to override defaults:

```bash
# API Configuration
export OPENAI_API_KEY="sk-your-key-here"
export ANTHROPIC_API_KEY="your-anthropic-key"
export AI_PROVIDER="openai"

# Processing Settings
export CONCURRENT_REQUESTS=3
export AI_REQUEST_DELAY=2.0
export USE_STEALTH_MODE=true

# Run with environment settings
uv run site-analyser analyze --urls-file urls.txt
```

## AI Configuration

### Provider Settings

**OpenAI (GPT-4):**
```json
{
  "ai_config": {
    "provider": "openai",
    "api_key": "sk-your-key-here",
    "model": "gpt-4o",
    "temperature": 0.1
  }
}
```

**Anthropic (Claude):**
```json
{
  "ai_config": {
    "provider": "anthropic", 
    "api_key": "your-anthropic-key",
    "model": "claude-sonnet-4-20250514",
    "temperature": 0.1
  }
}
```

### Model Options

| Provider | Models | Use Case |
|----------|---------|----------|
| OpenAI | `gpt-4o` | **Recommended** - Best vision analysis |
| OpenAI | `gpt-4o-mini` | Budget option, good performance |
| Anthropic | `claude-sonnet-4-20250514` | Alternative to GPT-4 |
| Anthropic | `claude-haiku-3-20240307` | Fastest, basic analysis |

### Advanced AI Settings

```json
{
  "ai_config": {
    "provider": "openai",
    "model": "gpt-4o",
    "max_tokens": 2000,
    "temperature": 0.05,
    
    "enable_reasoning": true,
    "enable_structured_output": true,
    "agent_memory": false
  }
}
```

## Processing Configuration

### Performance Settings

**High Performance (Less Reliable):**
```json
{
  "processing_config": {
    "concurrent_requests": 10,
    "request_timeout_seconds": 15,
    "ai_request_delay_seconds": 0.5,
    "use_stealth_mode": false,
    "simulate_human_behavior": false
  }
}
```

**High Reliability (Slower):**
```json
{
  "processing_config": {
    "concurrent_requests": 1,
    "request_timeout_seconds": 60,
    "ai_request_delay_seconds": 5.0,
    "use_stealth_mode": true,
    "simulate_human_behavior": true,
    "handle_captcha_challenges": true
  }
}
```

**Balanced (Recommended):**
```json
{
  "processing_config": {
    "concurrent_requests": 2,
    "request_timeout_seconds": 30,
    "ai_request_delay_seconds": 2.5,
    "use_stealth_mode": true,
    "random_user_agents": true,
    "simulate_human_behavior": false
  }
}
```

### Timeout Settings

| Setting | Min | Max | Recommended | Purpose |
|---------|-----|-----|-------------|---------|
| `request_timeout_seconds` | 5 | 120 | 30 | Page load timeout |
| `screenshot_timeout_seconds` | 5 | 60 | 15 | Screenshot capture |
| `ai_request_delay_seconds` | 0.1 | 10.0 | 2.5 | Delay between AI calls |
| `retry_delay_seconds` | 1 | 30 | 2 | Delay before retry |

### Retry Configuration

```json
{
  "processing_config": {
    "max_retries": 3,
    "retry_delay_seconds": 2
  }
}
```

## Bot Evasion Configuration

### Stealth Levels

**Maximum Stealth:**
```json
{
  "processing_config": {
    "use_stealth_mode": true,
    "random_user_agents": true,
    "simulate_human_behavior": true,
    "handle_captcha_challenges": true,
    "concurrent_requests": 1,
    "ai_request_delay_seconds": 4.0
  }
}
```

**Minimal Stealth:**
```json
{
  "processing_config": {
    "use_stealth_mode": true,
    "random_user_agents": true,
    "simulate_human_behavior": false,
    "handle_captcha_challenges": false,
    "concurrent_requests": 3
  }
}
```

**No Stealth (Fastest):**
```json
{
  "processing_config": {
    "use_stealth_mode": false,
    "random_user_agents": false,
    "simulate_human_behavior": false,
    "handle_captcha_challenges": false,
    "concurrent_requests": 10
  }
}
```

## Output Configuration

### Directory Structure

```json
{
  "output_config": {
    "results_directory": "./results",
    "screenshots_directory": "./results/screenshots",
    "json_output_file": "./results/analysis.json"
  }
}
```

Creates:
```
results/
├── analysis.json          # Main results
├── screenshots/           # Website screenshots
│   ├── example.com.png
│   └── another-site.com.png
```

### Storage Options

```json
{
  "output_config": {
    "keep_html": true,        # Save HTML content (large files)
    "keep_screenshots": true, # Save screenshots (recommended)
    "json_output_file": null  # Disable JSON output
  }
}
```

### Custom Paths

```json
{
  "output_config": {
    "results_directory": "/var/log/site-analyser",
    "screenshots_directory": "/var/log/site-analyser/images",
    "json_output_file": "/var/log/site-analyser/compliance.json"
  }
}
```

## Site-Specific Configuration

### URL Patterns

```json
{
  "urls": [
    "https://example.com",
    "https://another-site.com/path",
    "https://subdomain.example.org"
  ]
}
```

### Bulk URL Configuration

```json
{
  "urls": [
    "https://site1.com",
    "https://site2.com",
    "https://site3.com"
    // ... up to 1000+ URLs
  ],
  "processing_config": {
    "concurrent_requests": 5
  }
}
```

## Environment-Specific Configurations

### Development

```json
{
  "ai_config": {
    "provider": "openai",
    "model": "gpt-4o-mini"
  },
  "processing_config": {
    "concurrent_requests": 2,
    "ai_request_delay_seconds": 1.0,
    "use_stealth_mode": false
  },
  "output_config": {
    "keep_html": true,
    "keep_screenshots": true
  }
}
```

### Production

```json
{
  "ai_config": {
    "provider": "openai",
    "model": "gpt-4o"
  },
  "processing_config": {
    "concurrent_requests": 3,
    "ai_request_delay_seconds": 3.0,
    "use_stealth_mode": true,
    "simulate_human_behavior": true
  },
  "output_config": {
    "keep_html": false,
    "keep_screenshots": true,
    "results_directory": "/var/log/site-analyser"
  }
}
```

### CI/CD

```json
{
  "ai_config": {
    "provider": "openai",
    "model": "gpt-4o"
  },
  "processing_config": {
    "concurrent_requests": 1,
    "request_timeout_seconds": 60,
    "max_retries": 5,
    "use_stealth_mode": true
  }
}
```

## Configuration Validation

### Test Configuration

```bash
# Validate configuration file
uv run site-analyser analyze \
    --config config.json \
    --urls "https://httpbin.org/get" \
    --output-dir /tmp/config-test
```

### Debug Configuration

```bash
# Show effective configuration
uv run site-analyser --debug analyze \
    --config config.json \
    --urls "https://example.com"
```

## Configuration Templates

### HMRC Vendor Monitoring

```json
{
  "ai_config": {
    "provider": "openai",
    "model": "gpt-4o"
  },
  "processing_config": {
    "concurrent_requests": 2,
    "ai_request_delay_seconds": 3.0,
    "use_stealth_mode": true,
    "random_user_agents": true,
    "simulate_human_behavior": false,
    "handle_captcha_challenges": true
  },
  "output_config": {
    "results_directory": "./hmrc-compliance",
    "keep_screenshots": true
  }
}
```

### High-Volume Analysis

```json
{
  "ai_config": {
    "provider": "openai", 
    "model": "gpt-4o-mini"
  },
  "processing_config": {
    "concurrent_requests": 5,
    "ai_request_delay_seconds": 1.5,
    "use_stealth_mode": true,
    "simulate_human_behavior": false
  }
}
```

### Research/Academic

```json
{
  "ai_config": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "temperature": 0.0
  },
  "processing_config": {
    "concurrent_requests": 1,
    "ai_request_delay_seconds": 4.0,
    "use_stealth_mode": true,
    "simulate_human_behavior": true
  },
  "output_config": {
    "keep_html": true,
    "keep_screenshots": true
  }
}
```

## Troubleshooting Configuration

### Common Issues

**Rate Limits:**
```json
{
  "processing_config": {
    "ai_request_delay_seconds": 5.0,
    "concurrent_requests": 1
  }
}
```

**Timeouts:**
```json
{
  "processing_config": {
    "request_timeout_seconds": 60,
    "screenshot_timeout_seconds": 30
  }
}
```

**Bot Detection:**
```json
{
  "processing_config": {
    "use_stealth_mode": true,
    "simulate_human_behavior": true,
    "concurrent_requests": 1
  }
}
```

### Configuration Priority

1. **CLI arguments** (highest)
2. **Configuration file** 
3. **Environment variables**
4. **Default values** (lowest)

Example:
```bash
# This overrides config file settings
uv run site-analyser analyze \
    --config config.json \
    --concurrent-requests 1 \
    --ai-delay 5.0
```