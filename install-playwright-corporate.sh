#!/bin/bash

# Script to install Playwright browsers in corporate environments with certificate issues

echo "🏢 Installing Playwright for Corporate Environment"
echo "================================================"

# Set environment variables to handle certificate issues
export NODE_TLS_REJECT_UNAUTHORIZED=0
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

# Option 1: Try with disabled TLS verification
echo "🔧 Attempting installation with disabled TLS verification..."
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium

# Check if that worked
if [ $? -eq 0 ]; then
    echo "✅ Playwright installation successful!"
    echo "🎭 Testing Playwright installation..."
    uv run python -c "from playwright.async_api import async_playwright; print('Playwright import successful!')"
    exit 0
fi

# Option 2: Try with system certificates
echo "🔧 Attempting installation using system certificates..."
export PLAYWRIGHT_BROWSERS_PATH=/usr/local/lib/playwright
mkdir -p $PLAYWRIGHT_BROWSERS_PATH
NODE_TLS_REJECT_UNAUTHORIZED=0 PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_PATH uv run playwright install chromium

# Check if that worked
if [ $? -eq 0 ]; then
    echo "✅ Playwright installation successful with custom path!"
    exit 0
fi

# Option 3: Manual download approach
echo "🔧 Manual installation approach..."
echo "If automatic installation fails, you can:"
echo "1. Download browsers manually from a machine outside corporate network"
echo "2. Or ask IT to whitelist these domains:"
echo "   - https://storage.googleapis.com"
echo "   - https://github.com"
echo "   - https://playwright.azureedge.net"

# Option 4: Use existing system Chrome
echo "🔧 Alternative: Use system Chrome installation"
echo "You can also use your system Chrome browser by setting:"
echo "export PLAYWRIGHT_BROWSERS_PATH=/Applications/Google\\ Chrome.app/Contents/MacOS/"

exit 1