# Troubleshooting Guide

Solutions to common issues and problems when using Site Analyser.

## 🚨 Common Issues

### Installation Problems

#### "Python 3.11+ Required"

**Problem**: Python version too old
```bash
ERROR: Python 3.11+ required, found 3.9.7
```

**Solution**:
```bash
# macOS with Homebrew
brew install python@3.11

# Ubuntu/Debian
sudo apt install python3.11 python3.11-venv

# Windows - download from python.org

# Verify version
python3.11 --version
uv sync --python python3.11
```

#### "Playwright Browser Installation Failed"

**Problem**: Browser installation timeout or permission errors
```bash
ERROR: Download of chromium failed
```

**Solutions**:
```bash
# Retry with force flag
playwright install --force chromium

# Install with system dependencies (Ubuntu/Debian)
sudo playwright install-deps chromium
playwright install chromium

# Manual installation
npm install -g playwright
npx playwright install chromium

# Check disk space
df -h
```

#### "UV Command Not Found"

**Problem**: UV package manager not installed
```bash
bash: uv: command not found
```

**Solution**:
```bash
# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (restart terminal or source ~/.bashrc)
export PATH="$HOME/.cargo/bin:$PATH"

# Verify installation
uv --version
```

### Configuration Issues

#### "API Key Not Found"

**Problem**: Missing or invalid API keys
```bash
ERROR: OPENAI_API_KEY environment variable not set
```

**Solutions**:
```bash
# Check environment
echo $OPENAI_API_KEY

# Set in .env file
echo "OPENAI_API_KEY=sk-your-key-here" >> .env

# Set temporarily
export OPENAI_API_KEY="sk-your-key-here"

# Verify key format
# OpenAI: sk-...
# Anthropic: sk-ant-...
```

#### "Invalid Configuration File"

**Problem**: Malformed JSON configuration
```bash
ERROR: Invalid JSON in config file
```

**Solutions**:
```bash
# Validate JSON
python -m json.tool config.json

# Check for common issues:
# - Missing quotes around strings
# - Trailing commas
# - Incorrect nesting

# Use online JSON validator
# Generate from template
cp docs/examples/config-template.json config.json
```

### Runtime Errors

#### "SSL Certificate Error"

**Problem**: SSL verification failures
```bash
ERROR: SSL certificate verification failed
```

**Solutions**:
```bash
# Upgrade certificates
pip install --upgrade certifi

# Check system time (SSL certificates are time-sensitive)
date

# Temporary workaround (not recommended for production)
export PYTHONHTTPSVERIFY=0
```

#### "Rate Limit Exceeded"

**Problem**: API rate limits hit
```bash
ERROR: Rate limit exceeded for gpt-4o
```

**Solutions**:
```bash
# Increase delays
uv run site-analyser analyze \
    --ai-delay 5.0 \
    --concurrent-requests 1

# Use different model
uv run site-analyser analyze \
    --ai-provider anthropic

# Check API quotas in provider dashboard
```

#### "Memory Issues"

**Problem**: System running out of memory
```bash
MemoryError: Unable to allocate array
```

**Solutions**:
```bash
# Reduce concurrent requests
uv run site-analyser analyze \
    --concurrent-requests 1

# Disable HTML storage
uv run site-analyser analyze \
    --no-keep-html

# Monitor memory usage
top -p $(pgrep -f site-analyser)

# Close other applications
```

### Network Issues

#### "Connection Timeout"

**Problem**: Network timeouts during analysis
```bash
ERROR: Timeout after 30 seconds
```

**Solutions**:
```bash
# Increase timeout
uv run site-analyser analyze \
    --request-timeout 60

# Check network connectivity
curl -I https://openai.com
ping 8.8.8.8

# Use different DNS
export RESOLV_CONF="nameserver 1.1.1.1"
```

#### "Proxy Configuration"

**Problem**: Corporate firewall/proxy blocking requests
```bash
ERROR: Connection refused
```

**Solutions**:
```bash
# Set proxy environment variables
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080

# Configure proxy in browser context (edit web_scraper_agent.py)
context = await browser.new_context(
    proxy={
        "server": "http://proxy.company.com:8080"
    }
)

# Skip SSL verification for internal proxies
export NODE_TLS_REJECT_UNAUTHORIZED=0
```

### Bot Detection Issues

#### "All Sites Showing Bot Protection"

**Problem**: High bot detection rates
```bash
🚫 BOT PROTECTION DETECTED:
  • 8/10 sites blocked
```

**Solutions**:
```bash
# Enable maximum stealth
uv run site-analyser analyze \
    --stealth \
    --random-agents \
    --human-behavior \
    --handle-captcha \
    --concurrent-requests 1 \
    --ai-delay 4.0

# Try different times of day
# Run during off-peak hours

# Check IP reputation
curl https://www.whatismyipaddress.com/blacklist-check

# Consider VPN/proxy rotation (external tool)
```

#### "CAPTCHA Not Handled"

**Problem**: CAPTCHAs not being solved
```bash
INFO: bot_detection_wait detected, reason="captcha"
```

**Solutions**:
```bash
# Enable CAPTCHA handling
uv run site-analyser analyze \
    --handle-captcha

# Increase wait times
# Edit web_scraper_agent.py:
await asyncio.sleep(10)  # Longer CAPTCHA wait

# Manual intervention required for complex CAPTCHAs
# Consider CAPTCHA solving services (external)
```

### Performance Issues

#### "Analysis Too Slow"

**Problem**: Taking hours for small batches
```bash
INFO: Analysis estimated time: 2 hours for 10 sites
```

**Solutions**:
```bash
# Disable human behavior simulation
uv run site-analyser analyze \
    --no-human-behavior

# Reduce AI delays
uv run site-analyser analyze \
    --ai-delay 1.0

# Increase concurrency (if success rate allows)
uv run site-analyser analyze \
    --concurrent-requests 3

# Use faster model
uv run site-analyser analyze \
    --ai-provider openai
    # GPT-4o-mini for faster analysis
```

#### "High CPU Usage"

**Problem**: System overloaded during analysis
```bash
CPU usage: 100%
```

**Solutions**:
```bash
# Reduce concurrent requests
uv run site-analyser analyze \
    --concurrent-requests 1

# Limit browser resources
# Edit web_scraper_agent.py:
browser = await p.chromium.launch(
    args=["--memory-pressure-off", "--max_old_space_size=512"]
)

# Run with nice priority
nice -n 10 uv run site-analyser analyze
```

### Data Issues

#### "No Compliance Data Found"

**Problem**: All compliance fields showing as empty
```bash
Tax service relevant content: 0/10 (0.0%)
Fully functional websites: 0/10 (0.0%)
```

**Solutions**:
```bash
# Check if analysis agents are running
uv run site-analyser --debug analyze --urls "https://example.com"

# Look for agent errors in logs
grep "agent_exception" logs.txt

# Verify API keys work
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models

# Test with known working site
uv run site-analyser analyze --urls "https://httpbin.org/get"
```

#### "Screenshots Not Saving"

**Problem**: Screenshot directory empty
```bash
ls results/screenshots/
# Empty directory
```

**Solutions**:
```bash
# Check screenshot settings
uv run site-analyser analyze \
    --keep-screenshots

# Verify permissions
ls -la results/
mkdir -p results/screenshots
chmod 755 results/screenshots

# Check disk space
df -h

# Debug screenshot taking
uv run site-analyser --debug analyze --urls "https://example.com"
```

## 🔍 Debugging Techniques

### Enable Debug Logging

```bash
# Full debug output
uv run site-analyser --debug analyze --urls "https://example.com"

# Specific component logging
export PYTHONPATH="."
export LOG_LEVEL="DEBUG"
python -m site_analyser.main analyze --urls "https://example.com"
```

### Test Individual Components

```bash
# Test web scraping only
python -c "
from site_analyser.agents.web_scraper_agent import WebScraperAgent
from site_analyser.models.config import SiteAnalyserConfig
import asyncio

config = SiteAnalyserConfig()
agent = WebScraperAgent(config)
result = asyncio.run(agent.scrape_site('https://httpbin.org/get'))
print('Success:', result['success'])
"

# Test AI connectivity
python -c "
import openai
client = openai.OpenAI()
response = client.chat.completions.create(
    model='gpt-4o',
    messages=[{'role': 'user', 'content': 'Hello'}]
)
print('API works:', bool(response.choices))
"
```

### Check System Resources

```bash
# Memory usage
free -h

# Disk space
df -h

# Network connectivity
ping google.com

# Browser processes
ps aux | grep chrome

# Port conflicts
netstat -tulpn | grep :80
```

### Validate Input Data

```bash
# Check URL file format
cat urls.txt | head -5

# Validate URLs
python -c "
from pydantic import HttpUrl
urls = ['https://example.com', 'invalid-url']
for url in urls:
    try:
        HttpUrl(url)
        print(f'✅ {url}')
    except:
        print(f'❌ {url}')
"

# Test site accessibility
curl -I https://example.com
```

## 📊 Performance Tuning

### Optimal Settings by Use Case

**Development/Testing**:
```bash
uv run site-analyser analyze \
    --urls "https://example.com" \
    --no-stealth \
    --concurrent-requests 1 \
    --ai-delay 0.5 \
    --output-dir /tmp/test
```

**Production - Reliability**:
```bash
uv run site-analyser analyze \
    --urls-file production.txt \
    --stealth \
    --random-agents \
    --human-behavior \
    --concurrent-requests 1 \
    --ai-delay 3.0
```

**Production - Speed**:
```bash
uv run site-analyser analyze \
    --urls-file production.txt \
    --stealth \
    --no-human-behavior \
    --concurrent-requests 3 \
    --ai-delay 1.5
```

**High-Volume Analysis**:
```bash
uv run site-analyser analyze \
    --urls-file large-batch.txt \
    --no-stealth \
    --concurrent-requests 10 \
    --ai-delay 0.8
```

### Memory Optimization

```bash
# Disable HTML storage for large batches
uv run site-analyser analyze \
    --urls-file large-batch.txt \
    --no-keep-html

# Process in smaller batches
split -l 50 large-urls.txt batch-
for batch in batch-*; do
    uv run site-analyser analyze --urls-file "$batch"
done
```

## 🚑 Emergency Procedures

### Kill Hanging Analysis

```bash
# Find process
ps aux | grep site-analyser

# Kill gracefully
pkill -f site-analyser

# Force kill if needed
pkill -9 -f site-analyser

# Kill browser processes
pkill -f chromium
```

### Clean Up Resources

```bash
# Clear browser cache
rm -rf /tmp/.org.chromium.*

# Clear Python cache
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete

# Clear UV cache
uv cache clean
```

### Recovery from Corrupted State

```bash
# Reinstall dependencies
uv sync --reinstall

# Reinstall browsers
playwright install --force chromium

# Reset configuration
mv config.json config.json.backup
cp docs/examples/config-template.json config.json

# Verify clean installation
uv run site-analyser --help
```

## 📞 Getting Help

### Before Reporting Issues

1. **Update to latest version**
2. **Try with minimal configuration**
3. **Test with known-working URLs**
4. **Check system resources**
5. **Review logs for error patterns**

### Information to Include

When reporting issues, include:

- **Command used**: Full command line
- **System info**: OS, Python version, architecture
- **Error message**: Complete error output
- **Configuration**: Anonymized config file
- **Sample URLs**: Non-sensitive test URLs that reproduce issue
- **Timing**: When issue started occurring

### Log Collection

```bash
# Collect debug logs
uv run site-analyser --debug analyze \
    --urls "https://example.com" \
    --output-dir debug-results \
    2>&1 | tee debug.log

# System info
uname -a > system-info.txt
python --version >> system-info.txt
uv --version >> system-info.txt
```

### Community Resources

- **GitHub Issues**: Report bugs and feature requests
- **GitHub Discussions**: General questions and usage help
- **Documentation**: Comprehensive guides and examples