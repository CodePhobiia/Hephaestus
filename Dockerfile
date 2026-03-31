# ── Hephaestus — Docker Image ────────────────────────────────────────────────
# Python 3.12 slim base, installs hephaestus with web extras, runs uvicorn.

FROM python:3.12-slim

# System dependencies for sentence-transformers / numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for safety
RUN useradd -m -u 1000 heph
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY web/ ./web/

# Install hephaestus with web extras
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[web]"

# Ownership
RUN chown -R heph:heph /app
USER heph

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run server
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
