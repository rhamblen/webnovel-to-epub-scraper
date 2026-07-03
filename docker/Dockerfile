# Phase 0 uses a slim Python base. Phase 4 (JS-rendered sites) switches this to a
# Playwright-capable base image (e.g. mcr.microsoft.com/playwright/python) so the
# skeleton image stays small until browser rendering is actually needed.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8080
VOLUME ["/config", "/output"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
