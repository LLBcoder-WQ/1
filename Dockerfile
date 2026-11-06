FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SHOP_ENVIRONMENT=production \
    SHOP_DATABASE_URL=sqlite:////data/shop.db

WORKDIR /app
COPY pyproject.toml ./
COPY app/ ./app/
RUN pip install --no-cache-dir . \
    && addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /data \
    && chown app:app /data
COPY --from=frontend-build /frontend/dist/ ./frontend/dist/

USER app
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
