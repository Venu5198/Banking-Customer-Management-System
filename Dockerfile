# ─── Stage 1: Builder ────────────────────────────────────────────────────────
# Use a slim Python base to keep the final image small
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies required for psycopg2 (PostgreSQL driver)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching — only re-runs if requirements change)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir psycopg2-binary==2.9.9

# ─── Stage 2: Final Image ────────────────────────────────────────────────────
FROM python:3.11-slim AS final

WORKDIR /app

# Install libpq only (runtime dependency for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the full application source
COPY . .

# Create a non-root user for security — never run apps as root in production!
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# Expose the application port
EXPOSE 8000

# Health check — Docker will poll this to know if the container is healthy
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
