#!/bin/bash

# Quick DNF installation script for Playwright dependencies
# For RHEL 8/9, CentOS 8/9, Fedora

echo "🔧 Installing Playwright Dependencies with DNF"
echo "=============================================="

# Check if DNF is available
if ! command -v dnf &> /dev/null; then
    echo "❌ DNF not found. This script is for RHEL/CentOS/Fedora systems with DNF."
    echo "💡 For older systems, try YUM or the main install-linux-dependencies.sh script"
    exit 1
fi

# Update system
echo "📦 Updating system packages..."
sudo dnf update -y

# Install Playwright system dependencies
echo "📦 Installing Playwright system dependencies..."
sudo dnf install -y \
    wget \
    curl \
    ca-certificates \
    liberation-fonts \
    dejavu-sans-fonts \
    alsa-lib \
    at-spi2-atk \
    at-spi2-core \
    atk \
    gtk3 \
    libdrm \
    mesa-libgbm \
    libXcomposite \
    libXdamage \
    libXfixes \
    libXrandr \
    libXScrnSaver \
    libXtst \
    nss \
    nspr \
    libicu \
    libX11 \
    libxcb \
    libXcursor \
    libXext \
    libXi \
    libxkbcommon \
    libXrender \
    xorg-x11-server-Xvfb \
    openssl

if [ $? -ne 0 ]; then
    echo "❌ Failed to install system dependencies"
    echo "💡 Try installing Chrome instead: sudo dnf install -y google-chrome-stable"
    exit 1
fi

# Install Playwright dependencies
echo "🎭 Installing Playwright dependencies..."
uv run playwright install-deps chromium

if [ $? -ne 0 ]; then
    echo "⚠️  Playwright install-deps failed, but system packages are installed"
fi

# Install Playwright browsers (with certificate bypass)
echo "🌐 Installing Playwright browsers..."
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium

if [ $? -eq 0 ]; then
    echo "✅ Playwright installation completed successfully!"
else
    echo "❌ Playwright browser installation failed"
    echo "💡 Alternative: Install Chrome and use system browser"
    echo "   sudo dnf install -y google-chrome-stable"
    echo "   export USE_SYSTEM_CHROME=true"
    exit 1
fi

# Test installation
echo "🧪 Testing Playwright installation..."
uv run python -c "
import asyncio
from playwright.async_api import async_playwright

async def test():
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto('https://example.com')
            print('✅ Playwright test successful!')
            await browser.close()
    except Exception as e:
        print(f'❌ Playwright test failed: {e}')
        print('💡 Try: export USE_SYSTEM_CHROME=true')

asyncio.run(test())
"

echo "🎉 Installation complete!"
echo ""
echo "📋 Next steps:"
echo "  # Test screenshot functionality"
echo "  uv run site-analyser screenshot --urls https://example.com --verbose"
echo ""
echo "  # If issues persist, use system Chrome:"
echo "  sudo dnf install -y google-chrome-stable"
echo "  export USE_SYSTEM_CHROME=true"