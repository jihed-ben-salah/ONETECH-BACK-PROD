# Multi-stage build for extraction_api
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    DJANGO_SETTINGS_MODULE=core.settings

WORKDIR /app

# System deps (minimal for PyMuPDF - no poppler needed!)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy only app code (avoid bringing whole monorepo to keep image smaller)
COPY core ./core
COPY extraction ./extraction
COPY manage.py ./
COPY process_forms.py ./process_forms.py
COPY vercel_handler.py ./vercel_handler.py

# Collect static files and create necessary directories
RUN mkdir -p /app/staticfiles && \
    mkdir -p /app/media/images && \
    python manage.py collectstatic --noinput --clear || true && \
    chmod -R 755 /app/staticfiles && \
    chmod -R 755 /app/media

EXPOSE 8000

# Healthcheck using python instead of curl
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

# Default command with proper error handling
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "600", "--worker-class", "sync", "--max-requests", "1000", "--max-requests-jitter", "100"]
