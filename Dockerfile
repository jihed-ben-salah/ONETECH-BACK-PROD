# Multi-stage build for extraction_api
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# System deps (add libgl if opencv needs it, poppler-utils for pdf2image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
    poppler-utils \
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

# Collect static (if needed) - safe even if no static
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Healthcheck (simple)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:8000/health/ || exit 1

# Default command
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "600"]
