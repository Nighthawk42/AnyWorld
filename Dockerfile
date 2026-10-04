FROM python:3.12-slim

# Install system dependencies including curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and build tools
RUN pip install --no-cache-dir --upgrade pip setuptools hatchling

# Copy project specification first for optimal layer caching
COPY pyproject.toml README.md ./

# Copy application source code and assets
COPY app.py config.example.yaml ./
COPY api/ ./api/
COPY core/ ./core/
COPY logic/ ./logic/
COPY static/ ./static/
COPY templates/ ./templates/

# Install application and production dependencies
RUN pip install --no-cache-dir .

# Create persistent state directories and dedicated non-root service user
RUN mkdir -p /app/.logged_games /app/.public_games /app/certs /app/.debug && \
    useradd --system --uid 10001 --home /app anyworld && \
    chown -R anyworld:anyworld /app

USER anyworld

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 4141

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -k -f https://localhost:4141/ || exit 1

ENTRYPOINT ["python", "app.py"]
CMD ["--host", "0.0.0.0", "--port", "4141"]
