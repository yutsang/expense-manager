FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache)
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[prod]" 2>/dev/null || pip install --no-cache-dir .

# Copy app
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Non-root user
RUN useradd -m -u 1000 aegis && chown -R aegis:aegis /app
USER aegis

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
