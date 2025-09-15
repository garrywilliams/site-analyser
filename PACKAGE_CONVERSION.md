# Package Name Conversion: APT vs DNF

## Playwright Dependencies Package Mapping

| Debian/Ubuntu (apt-get) | RHEL/CentOS/Fedora (dnf/yum) | Description |
|--------------------------|-------------------------------|-------------|
| `wget` | `wget` | Download utility |
| `gnupg` | `gnupg2` | GNU Privacy Guard |
| `ca-certificates` | `ca-certificates` | Certificate authorities |
| `fonts-liberation` | `liberation-fonts` | Liberation fonts |
| `libasound2` | `alsa-lib` | ALSA sound library |
| `libatk-bridge2.0-0` | `at-spi2-atk` | ATK bridge library |
| `libatk1.0-0` | `atk` | ATK accessibility library |
| `libatspi2.0-0` | `at-spi2-core` | AT-SPI core library |
| `libdrm2` | `libdrm` | Direct Rendering Manager |
| `libgtk-3-0` | `gtk3` | GTK+ 3 library |
| `libicu66` | `libicu` | International Components for Unicode |
| `libnspr4` | `nspr` | Netscape Portable Runtime |
| `libnss3` | `nss` | Network Security Services |
| `libxcomposite1` | `libXcomposite` | X Composite extension |
| `libxdamage1` | `libXdamage` | X Damage extension |
| `libxfixes3` | `libXfixes` | X Fixes extension |
| `libxrandr2` | `libXrandr` | X RandR extension |
| `libxss1` | `libXScrnSaver` | X Screen Saver extension |
| `libxtst6` | `libXtst` | X Test extension |
| `xvfb` | `xorg-x11-server-Xvfb` | Virtual framebuffer |
| `openssl` | `openssl` | SSL/TLS library |
| `libgbm1` | `mesa-libgbm` | Mesa Graphics Buffer Manager |
| `libxkbcommon0` | `libxkbcommon` | XKB common library |

## Complete DNF Installation Commands

### For RHEL 8/9, CentOS 8/9, Fedora:

```bash
# Update system
sudo dnf update -y

# Install Playwright system dependencies
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
    libXcb \
    libXcursor \
    libXext \
    libXi \
    libxkbcommon \
    libXrender \
    xorg-x11-server-Xvfb \
    openssl

# Install Playwright dependencies and browsers
uv run playwright install-deps chromium
NODE_TLS_REJECT_UNAUTHORIZED=0 uv run playwright install chromium
```

### For CentOS 7 (YUM):

```bash
# Enable EPEL repository for additional packages
sudo yum install -y epel-release

# Update system
sudo yum update -y

# Install dependencies
sudo yum install -y \
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
```

## Alternative: Install Chrome/Chromium Instead

### RHEL/CentOS/Fedora Chrome Installation:

```bash
# Add Google Chrome repository
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
sudo dnf install -y google-chrome-stable

# OR install Chromium
sudo dnf install -y chromium

# Use system Chrome
export USE_SYSTEM_CHROME=true
```

## Package Manager Detection Script

```bash
#!/bin/bash

# Detect package manager and install accordingly
if command -v dnf &> /dev/null; then
    echo "Using DNF package manager"
    PKG_MANAGER="dnf"
    INSTALL_CMD="sudo dnf install -y"
elif command -v yum &> /dev/null; then
    echo "Using YUM package manager"
    PKG_MANAGER="yum"
    INSTALL_CMD="sudo yum install -y"
    # Enable EPEL for CentOS 7
    sudo yum install -y epel-release
elif command -v apt-get &> /dev/null; then
    echo "Using APT package manager"
    PKG_MANAGER="apt-get"
    INSTALL_CMD="sudo apt-get install -y"
    sudo apt-get update
else
    echo "No supported package manager found"
    exit 1
fi
```