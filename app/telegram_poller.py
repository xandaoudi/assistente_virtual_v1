"""Poller do Telegram — processo próprio, nunca embutido na API (T3.6).

`uv run python -m app.telegram_poller`. Roda em processo próprio de propósito: se rodasse
dentro dos workers do uvicorn, cada worker chamaria `getUpdates` e o usuário receberia
resposta duplicada — mesmo problema do scheduler da Etapa 6. Em produção (`TELEGRAM_MODE=
webhook`) ele simplesmente não sobe.

T3.14: liga o pipeline de produção completo (identidade, agente, tools, degradação, uso —
T3.8-T3.10) ao mesmo `handle_and_reply` que o webhook usa (T3.7), para que polling e webhook
respondam de forma idêntica — só a porta de entrada muda.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.adapters.channel_message import ChannelMessage
from app.adapters.production import build_production_pipeline
from app.adapters.telegram import (
    HttpTelegramUpdateSource,
    TelegramClient,
    TelegramSender,
    handle_and_reply,
    run_polling_loop,
)
from app.core.asyncio_loop import loop_factory
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _build_handler(
    pipeline_handler: Callable[[ChannelMessage], Awaitable[str | None]],
    telegram_client: TelegramSender,
) -> Callable[[ChannelMessage], Awaitable[None]]:
    async def handler(message: ChannelMessage) -> None:
        await handle_and_reply(message, pipeline_handler, telegram_client)

    return handler


async def _main() -> None:
    settings = get_settings()
    if settings.telegram_mode != "polling":
        raise RuntimeError(
            f"TELEGRAM_MODE={settings.telegram_mode!r} — o poller só roda com 'polling'; "
            "em produção o Telegram usa webhook (T3.7)."
        )
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN é obrigatório para rodar o poller.")

    logging.basicConfig(level=settings.log_level)
    source = HttpTelegramUpdateSource(settings.telegram_bot_token)
    telegram_client = TelegramClient(settings.telegram_bot_token)
    pipeline_handler = build_production_pipeline(
        max_history_messages=settings.conversation_history_window
    )
    await run_polling_loop(source, _build_handler(pipeline_handler, telegram_client))


def main() -> None:
    asyncio.run(_main(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
