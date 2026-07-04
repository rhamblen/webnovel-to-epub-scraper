# Phase 4 (JS-rendered sites): the official Playwright image, pre-installed with Python
# 3.12, headless Chromium, and its OS-level dependencies (an Ubuntu Noble/24.04 base) —
# no separate `playwright install` step needed. Version pinned exactly to match the
# `playwright` package version in requirements.txt (see the comment there); bump both
# together. Bigger than the old python:3.12-slim base (browsers add well over 1GB), but
# the browser process itself is still only launched lazily, on the first page that
# actually needs rendering (see core/render.py).
FROM mcr.microsoft.com/playwright/python:v1.61.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080
VOLUME ["/config", "/output"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
