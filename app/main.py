import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.adapters.production import build_production_pipeline
from app.adapters.telegram import TelegramClient
from app.api.telegram_webhook import build_telegram_webhook_router
from app.core.config import Settings, get_settings
from app.core.db import get_session_maker

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """`settings=None` usa `get_settings()`, mas nunca deixa uma falha de config impedir a
    aplicação de subir: `/health` (liveness pura) não pode passar a exigir configuração
    que ela nunca tocou antes."""
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready() -> JSONResponse:
        try:
            async with get_session_maker()() as session:
                await session.execute(text("SELECT 1"))
        except Exception:  # qualquer falha de conexão com o banco vira 503
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    if settings is None:
        try:
            settings = get_settings()
        except Exception:
            settings = None

    if (
        settings is not None
        and settings.telegram_mode == "webhook"
        and settings.telegram_webhook_secret
    ):
        telegram_client = TelegramClient(settings.telegram_bot_token or "")
        handler = build_production_pipeline(
            max_history_messages=settings.conversation_history_window
        )
        app.include_router(
            build_telegram_webhook_router(
                webhook_secret=settings.telegram_webhook_secret,
                handler=handler,
                telegram_client=telegram_client,
            )
        )

    return app


app = create_app()
