# ── Hephaestus — Multi-stage Docker Image ────────────────────────────────────

# ── Builder Stage ────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# System dependencies required for compiling extensions (e.g. numpy/pydantic)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy project files needed for build
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Create a virtual environment and install exactly the package + web extras
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[web]"

# ── Runtime Stage ────────────────────────────────────────────────────────
FROM python:3.12-slim

# Only curl is needed for the container HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd -m -u 1000 heph
WORKDIR /app

# Copy the pre-built virtual environment from the builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy runtime application files
COPY src/ ./src/
COPY web/ ./web/

# Ensure proper permissions
RUN chown -R heph:heph /app
USER heph

EXPOSE 8000

# Health check utilizing the Readiness/Health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Launch uvicorn
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
