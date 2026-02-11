# ResearchShop Disease2Gene Pipeline
# Multi-stage Docker image for the gene-disease extraction pipeline + web GUI

# ── Stage 1: Builder ─────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for Playwright and general operation
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright dependencies
    wget \
    gnupg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    # Additional utilities
    ca-certificates \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built Python packages from builder stage
COPY --from=builder /install /usr/local

# Install Playwright browsers (Chromium only for efficiency)
RUN playwright install chromium \
    && playwright install-deps chromium

# Copy application code
COPY modules/ ./modules/
COPY gui/ ./gui/
COPY data/reference/ ./data/reference/

# Create output directory
RUN mkdir -p data/output

# Set environment variables
ENV OUTPUT_DIR=/app/data/output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8050
ENV HOST=0.0.0.0

# Expose the web GUI port
EXPOSE 8050

# Health check - verify Flask app can respond
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/')" || exit 1

# Run the Flask web GUI (bind to 0.0.0.0 so it's accessible outside the container)
CMD ["python", "gui/app_server.py"]
