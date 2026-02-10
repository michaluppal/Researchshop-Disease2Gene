# ResearchShop Disease2Gene Pipeline
# Docker image for running the gene-disease extraction pipeline

FROM python:3.11-slim

# Set working directory
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

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only for efficiency)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY modules/ ./modules/
COPY run_local.py .
COPY data/reference/ ./data/reference/

# Create output directory
RUN mkdir -p data/output

# Set environment variables
ENV OUTPUT_DIR=/app/data/output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Health check - verify Python and Playwright are working
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import modules.config; print('OK')" || exit 1

# Default entrypoint
ENTRYPOINT ["python", "run_local.py"]

# Default command (can be overridden)
CMD ["--help"]

