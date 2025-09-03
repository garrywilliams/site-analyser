# Multi-stage build for site-analyser
FROM python:3.11-slim AS builder

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./
COPY site_analyser/ ./site_analyser/

# Install dependencies and build wheel
RUN uv venv /opt/venv
RUN uv pip install -e .

# Production stage
FROM python:3.11-slim

# Install system dependencies for Playwright and SSL
RUN apt-get update && apt-get install -y \
    # Playwright browser dependencies
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libdrm2 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    xvfb \
    # SSL/TLS support
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Create non-root user
RUN useradd --create-home --shell /bin/bash app
WORKDIR /home/app

# Copy application
COPY --chown=app:app site_analyser/ ./site_analyser/
COPY --chown=app:app pyproject.toml ./

# Create directories for results
RUN mkdir -p results/screenshots && chown -R app:app results/

USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import site_analyser; print('OK')" || exit 1

# Default command
ENTRYPOINT ["python", "-m", "site_analyser.main"]