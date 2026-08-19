# Imagem multi-stage para o Assistente Virtual.
# Compatível com ARM64 (Ampere A1 da Oracle) e AMD64 — a base python:slim
# publica ambas as arquiteturas, então o mesmo Dockerfile serve para os dois.

# ---------- Stage 1: builder ----------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential e libpq-dev são necessários para compilar wheels que ainda
# não têm build pronto para ARM64.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=UTC

# libpq5 = runtime do driver Postgres. tzdata = conversão de fuso (RF-12).
# curl = usado pelo healthcheck e por diagnóstico.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        tzdata \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Nunca rodar como root (RNF-07).
RUN groupadd --gid 1001 app \
    && useradd --uid 1001 --gid app --create-home --shell /bin/bash app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

RUN mkdir -p /app/media && chown -R app:app /app/media
USER app

EXPOSE 8000

# 2 workers: a VM Always Free tem 2 OCPU. O scheduler roda em container
# separado, então subir workers aqui não duplica lembretes.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
