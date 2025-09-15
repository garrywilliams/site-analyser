#!/bin/bash

# Script to install Playwright system dependencies on Linux

echo "🐧 Installing Playwright Dependencies for Linux"
echo "=============================================="

# Detect Linux distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
    VERSION=$VERSION_ID
else
    echo "❌ Cannot detect Linux distribution"
    exit 1
fi

echo "📋 Detected: $DISTRO $VERSION"

# Install dependencies based on distribution
case $DISTRO in
    "ubuntu"|"debian")
        echo "🔧 Installing dependencies for Ubuntu/Debian..."
        
        # Update package list
        sudo apt-get update
        
        # Install Playwright system dependencies
        sudo apt-get install -y \
            libicu66 \
            libicu-dev \
            libnss3 \
            libnspr4 \
            libatk-bridge2.0-0 \
            libdrm2 \
            libxkbcommon0 \
            libxcomposite1 \
            libxdamage1 \
            libxrandr2 \
            libgbm1 \
            libxss1 \
            libasound2 \
            libatspi2.0-0 \
            libgtk-3-0
        
        # Alternative: Use Playwright's built-in dependency installer
        echo "🎭 Installing Playwright system dependencies..."
        uv run playwright install-deps chromium
        ;;
        
    "centos"|"rhel"|"fedora")
        echo "🔧 Installing dependencies for RHEL/CentOS/Fedora..."
        
        if command -v dnf &> /dev/null; then
            PKG_MANAGER="dnf"
        elif command -v yum &> /dev/null; then
            PKG_MANAGER="yum"
            # Enable EPEL repository for CentOS 7
            echo "📦 Enabling EPEL repository..."
            sudo yum install -y epel-release || true
        else
            echo "❌ No package manager found"
            exit 1
        fi
        
        echo "📦 Using package manager: $PKG_MANAGER"
        
        # Update system first
        sudo $PKG_MANAGER update -y
        
        # Install comprehensive Playwright dependencies
        sudo $PKG_MANAGER install -y \
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
        
        # Use Playwright's built-in dependency installer
        echo "🎭 Installing Playwright system dependencies..."
        uv run playwright install-deps chromium
        ;;
        
    "alpine")
        echo "🔧 Installing dependencies for Alpine Linux..."
        
        sudo apk add --no-cache \
            icu-libs \
            icu-data-full \
            nss \
            freetype \
            harfbuzz \
            ca-certificates \
            ttf-freefont \
            chromium
        
        # Set Chromium path for Alpine
        export PLAYWRIGHT_BROWSERS_PATH=/usr/bin
        export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
        ;;
        
    *)
        echo "❓ Unknown distribution: $DISTRO"
        echo "📋 Trying generic approach..."
        
        # Try Playwright's built-in dependency installer
        uv run playwright install-deps chromium
        ;;
esac

echo "✅ Dependencies installation completed"
echo "🎭 Now installing Playwright browsers..."

# Install Playwright browsers
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium

echo "🧪 Testing Playwright installation..."
uv run python -c "
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://example.com')
        print('✅ Playwright test successful!')
        await browser.close()

asyncio.run(test())
"

if [ $? -eq 0 ]; then
    echo "🎉 Playwright installation and test successful!"
else
    echo "❌ Playwright test failed. You may need additional dependencies."
    echo "💡 Try using system Chrome with: export USE_SYSTEM_CHROME=true"
fi