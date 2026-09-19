# Multi-stage build: keeps the final image small by not shipping
# build tools (gcc etc. needed to compile psycopg2) into production.
FROM python:3.12-slim AS builder

WORKDIR /build

# psycopg2 (not -binary) would need libpq-dev, but we use psycopg2-binary
# which ships precompiled wheels - so we don't even need gcc here.
# Kept as a separate stage anyway so adding a C-extension dependency
# later doesn't bloat the runtime image.
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.12-slim

# Cloud Run injects PORT at runtime; default to 8080 for local `docker run`.
ENV PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/appuser/.local/bin:$PATH

# Run as a non-root user - Cloud Run and most container security
# scanners flag root containers.
RUN useradd --create-home --shell /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --chown=appuser:appuser app ./app

EXPOSE 8080

# Shell form so ${PORT} expands - required because Cloud Run assigns
# the port dynamically and overrides it via the PORT env var.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
