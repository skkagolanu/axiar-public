# Multi-stage production Dockerfile
FROM python:3.12-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to latest version
RUN pip install --no-cache-dir --upgrade pip==26.0.1

# Set working directory
WORKDIR /app

# Add PATH for pip user installs to suppress warnings
ENV PATH=/root/.local/bin:$PATH

# Copy requirements and install dependencies
COPY requirements.txt .
# Install the pinned backend requirements.
RUN pip install --no-cache-dir --user --root-user-action=ignore -r requirements.txt

# Production stage
FROM python:3.12-slim as runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r axiar && useradd -r -g axiar axiar

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder --chown=axiar:axiar /root/.local /home/axiar/.local

# Copy application code
COPY --chown=axiar:axiar . .

# Switch to non-root user
USER axiar

# Add local bin to PATH
ENV PATH=/home/axiar/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
