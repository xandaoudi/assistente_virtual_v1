# syntax=docker/dockerfile:1
#
# Build multi-estagio, compativel com amd64 e arm64 (a VPS de producao roda
# arm64 — ver deployment.md).
#
# Instalacao a partir do uv.lock via `uv sync --frozen`: usa exatamente as
# versoes travadas, sem resolver de novo. A alternativa mais conservadora
# (`uv export` -> `pip install`, sem uv na imagem final) foi verificada e
# tambem funciona; ficamos com uv por simplicidade e por ja ser a ferramenta
# usada em todo o resto do projeto — ela nao entra na imagem final, so na
# etapa de build.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.15 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# So as dependencias primeiro: mudar codigo depois nao invalida esta
# camada, e o `uv sync` nao roda de novo no rebuild.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

# Aponta para /health (liveness, sem tocar no banco) — nunca /health/ready.
# Ver T0.8: se o healthcheck consultasse o banco, uma indisponibilidade
# momentanea do Postgres derrubaria o container em loop.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"]

# `--loop`: o uvicorn escolhe ProactorEventLoop por padrao no Windows, mas
# em produção (Linux) o SelectorEventLoop já seria o default mesmo sem essa
# flag — ela so garante que dev e produção rodem com o mesmo comando
# (ver app/core/asyncio_loop.py e README.md).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--loop", "app.core.asyncio_loop:loop_factory"]
