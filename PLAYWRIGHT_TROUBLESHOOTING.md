# Playwright Installation Troubleshooting

## Corporate/Enterprise Environment Issues

### Issue 1: Certificate Errors (`SELF_SIGNED_CERT_IN_CHAIN`)

**Solution:**
```bash
# Bypass TLS verification during installation
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium
```

### Issue 2: Host Validation Warning + Missing Libraries

**Symptoms:**
- `Playwright Host validation warning`
- Missing libraries: `libicudata.so.66`, `libnss3.so`, etc.

**Solutions:**

#### Option 1: Install System Dependencies (Recommended)
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y libicu66 libnss3 libnspr4 libatk-bridge2.0-0 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
  libgbm1 libxss1 libasound2 libatspi2.0-0 libgtk-3-0

# Use Playwright's built-in dependency installer
uv run playwright install-deps chromium
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium

# CentOS/RHEL/Fedora
sudo dnf install -y libicu nss nspr at-spi2-atk libdrm libxkbcommon \
  libxcomposite libxdamage libxrandr mesa-libgbm libXScrnSaver \
  alsa-lib at-spi2-core gtk3

uv run playwright install-deps chromium
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium
```

#### Option 2: Use System Chrome (No Dependencies)
```bash
# Install Chrome/Chromium via package manager
sudo apt-get install -y google-chrome-stable
# OR
sudo apt-get install -y chromium-browser

# Use system Chrome
export USE_SYSTEM_CHROME=true
uv run site-analyser screenshot --urls https://example.com
```

#### Option 3: Use Installation Script
```bash
# Make script executable
chmod +x install-linux-dependencies.sh

# Run installation script
./install-linux-dependencies.sh
```

## Testing Your Installation

```bash
# Test Playwright import
uv run python -c "from playwright.async_api import async_playwright; print('✅ Playwright OK')"

# Test screenshot functionality
uv run site-analyser screenshot --urls https://example.com --verbose

# Test with system Chrome
USE_SYSTEM_CHROME=true uv run site-analyser screenshot --urls https://example.com --verbose
```

## Common Issues and Solutions

### Issue: `Cannot find Chrome executable`

**Solution:**
```bash
# Find Chrome installation
which google-chrome-stable
which chromium-browser
which chromium

# Set environment variable
export USE_SYSTEM_CHROME=true
```

### Issue: `Permission denied accessing /dev/shm`

**Solution:**
```bash
# Add to Chrome args (already included in our implementation)
--disable-dev-shm-usage
--no-sandbox
```

### Issue: `Xvfb not found` (Headless environments)

**Solution:**
```bash
# Install virtual framebuffer
sudo apt-get install -y xvfb

# Or run with headless Chrome (already our default)
```

### Issue: Corporate proxy blocking downloads

**Solutions:**
1. **Use system Chrome:** `export USE_SYSTEM_CHROME=true`
2. **Ask IT to whitelist:**
   - `https://storage.googleapis.com`
   - `https://github.com`
   - `https://playwright.azureedge.net`
3. **Manual transfer:** Download browsers on a different machine and copy

## Environment Variables Reference

```bash
# Corporate certificate issues
export NODE_TLS_REJECT_UNAUTHORIZED=0

# Use system Chrome instead of downloading
export USE_SYSTEM_CHROME=true

# Custom Playwright browser path
export PLAYWRIGHT_BROWSERS_PATH=/path/to/browsers

# Custom Chrome executable
export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
```

## Docker/Container Specific

If running in containers, ensure your Dockerfile includes:

```dockerfile
RUN apt-get update && apt-get install -y \
    libicu66 libnss3 libnspr4 libatk-bridge2.0-0 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libxss1 libasound2 libatspi2.0-0 \
    libgtk-3-0 fonts-liberation xvfb

RUN playwright install-deps chromium
RUN playwright install chromium
```

## Still Having Issues?

1. **Check system info:**
   ```bash
   uv run playwright --version
   ldd --version
   cat /etc/os-release
   ```

2. **Enable debug logging:**
   ```bash
   uv run site-analyser screenshot --urls https://example.com --verbose --debug
   ```

3. **Try minimal test:**
   ```bash
   uv run python -c "
   import asyncio
   from playwright.async_api import async_playwright
   
   async def test():
       async with async_playwright() as p:
           browser = await p.chromium.launch(headless=True)
           print('✅ Browser launched successfully')
           await browser.close()
   
   asyncio.run(test())
   "
   ```