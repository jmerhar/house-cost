# The application as one image: the API and the built interface it serves.

# The interface, built once; only the result goes into the image.
FROM node:24-alpine AS frontend
WORKDIR /build
# A registry can be supplied for a network that proxies npm; unset, frontend/.npmrc's is used.
ARG NPM_REGISTRY=""
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN if [ -n "$NPM_REGISTRY" ]; then npm ci --registry="$NPM_REGISTRY" --no-audit --no-fund; \
    else npm ci --no-audit --no-fund; fi
COPY frontend/ ./
RUN npm run build


FROM python:3.14-slim AS app

# Tesseract reads the bills whose PDFs carry no usable text, in Portuguese and English.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # No .pyc files, so the image runs with a read-only root filesystem.
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    STATIC_DIR=/app/web

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/src ./src
RUN pip install .
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY --from=frontend /build/dist ./web
COPY bin/entrypoint.sh /usr/local/bin/entrypoint.sh

# Unprivileged, so everything written into the mounted data directory belongs to a real account
# on the host rather than to root.
RUN mkdir -p /data && chown 1000:1000 /data
USER 1000:1000

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-m", "house_cost.healthcheck"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
