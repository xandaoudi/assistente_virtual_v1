"""Poller do Telegram — processo próprio, nunca embutido na API (T3.6).

`uv run python -m app.telegram_poller`. Roda em processo próprio de propósito: se rodasse
dentro dos workers do uvicorn, cada worker chamaria `getUpdates` e o usuário receberia
resposta duplicada — mesmo problema do scheduler da Etapa 6. Em produção (`TELEGRAM_MODE=
webhook`) ele simplesmente não sobe.

O handler abaixo ainda é um placeholder: a resolução de `chat_id` -> `user_id` (T3.8) e a
ligação com o agente (T3.1-T3.5) entram depois. Por ora isso prova que o laço de polling
funciona de ponta a ponta contra a Bot API real, com a mesma conversão para
`ChannelMessage` que o webhook (T3.7) vai usar.
"""

import asyncio
import logging

from app.adapters.channel_message import ChannelMessage
from app.adapters.telegram import HttpTelegramUpdateSource, run_polling_loop
from app.core.asyncio_loop import loop_factory
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def _handler_provisorio(message: ChannelMessage) -> None:
    logger.info(
        "mensagem recebida do telegram: channel=%s external_user_id=%s message_id=%s has_text=%s",
        message.channel,
        message.external_user_id,
        message.message_id,
        message.text is not None,
    )


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
    await run_polling_loop(source, _handler_provisorio)


def main() -> None:
    asyncio.run(_main(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
