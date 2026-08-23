"""T3.7 — e2e: fluxo completo do webhook do Telegram até o envio da resposta, dublado."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.adapters.channel_message import ChannelMessage
from app.api.telegram_webhook import build_telegram_webhook_router

pytestmark = pytest.mark.e2e

_SECRET = "segredo-e2e"
_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _update_de_texto(
    update_id: int = 1, texto: str = "gastei 45 no mercado ontem"
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": 777, "type": "private"},
            "date": 1735000000,
            "text": texto,
        },
    }


class _TelegramSenderDublado:
    def __init__(self) -> None:
        self.chat_actions: list[tuple[str, str]] = []
        self.mensagens_enviadas: list[tuple[str, str]] = []
        self.concluido = asyncio.Event()

    async def send_chat_action(self, chat_id: str, action: str) -> None:
        self.chat_actions.append((chat_id, action))

    async def send_message(self, chat_id: str, text: str) -> None:
        self.mensagens_enviadas.append((chat_id, text))
        self.concluido.set()


@pytest.mark.asyncio
async def test_fluxo_completo_do_webhook_ate_o_envio_da_resposta() -> None:
    sender = _TelegramSenderDublado()
    textos_recebidos: list[str | None] = []

    async def handler(message: ChannelMessage) -> str | None:
        textos_recebidos.append(message.text)
        return "Registrado: R$ 45,00 no mercado."

    app = FastAPI()
    app.include_router(
        build_telegram_webhook_router(
            webhook_secret=_SECRET, handler=handler, telegram_client=sender
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resposta = await client.post(
            f"/webhook/telegram/{_SECRET}",
            json=_update_de_texto(),
            headers={_HEADER: _SECRET},
        )
        assert resposta.status_code == 200
        assert resposta.json() == {"ok": True}

        await asyncio.wait_for(sender.concluido.wait(), timeout=2.0)

    assert textos_recebidos == ["gastei 45 no mercado ontem"]
    assert sender.chat_actions == [("777", "typing")]
    # "$" não é reservado no MarkdownV2 — só o "." final é escapado.
    assert sender.mensagens_enviadas == [("777", "Registrado: R$ 45,00 no mercado\\.")]
