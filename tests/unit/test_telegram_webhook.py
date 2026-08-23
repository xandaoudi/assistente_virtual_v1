"""T3.7 — webhook do Telegram: confirmação imediata e processamento em segundo plano."""

import asyncio
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.channel_message import ChannelMessage
from app.api.telegram_webhook import MessageHandler, TelegramSender, build_telegram_webhook_router
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.unit

_SECRET = "segredo-de-teste"
_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _update_de_texto(update_id: int = 1, texto: str = "oi") -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "chat": {"id": 555, "type": "private"},
            "date": 1735000000,
            "text": texto,
        },
    }


class _TelegramSenderFalso:
    def __init__(self) -> None:
        self.chat_actions: list[tuple[str, str]] = []
        self.mensagens_enviadas: list[tuple[str, str]] = []

    async def send_chat_action(self, chat_id: str, action: str) -> None:
        self.chat_actions.append((chat_id, action))

    async def send_message(self, chat_id: str, text: str) -> None:
        self.mensagens_enviadas.append((chat_id, text))


def _app_de_teste(handler: MessageHandler, sender: TelegramSender | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(
        build_telegram_webhook_router(
            webhook_secret=_SECRET,
            handler=handler,
            telegram_client=sender or _TelegramSenderFalso(),
        )
    )
    return app


async def _handler_padrao(message: ChannelMessage) -> str | None:
    return "resposta padrão"


def test_requisicao_sem_header_secreto_e_rejeitada() -> None:
    app = _app_de_teste(_handler_padrao)

    with TestClient(app) as client:
        resposta = client.post(f"/webhook/telegram/{_SECRET}", json=_update_de_texto())

    assert resposta.status_code in (401, 403)


def test_header_com_valor_errado_e_rejeitado() -> None:
    app = _app_de_teste(_handler_padrao)

    with TestClient(app) as client:
        resposta = client.post(
            f"/webhook/telegram/{_SECRET}",
            json=_update_de_texto(),
            headers={_HEADER: "valor-errado"},
        )

    assert resposta.status_code in (401, 403)


def test_webhook_responde_rapido_mesmo_com_processamento_lento_simulado() -> None:
    async def handler_lento(message: ChannelMessage) -> str | None:
        await asyncio.sleep(10)
        return "ok"

    app = _app_de_teste(handler_lento)

    with TestClient(app) as client:
        inicio = time.monotonic()
        resposta = client.post(
            f"/webhook/telegram/{_SECRET}",
            json=_update_de_texto(),
            headers={_HEADER: _SECRET},
        )
        decorrido = time.monotonic() - inicio

    assert resposta.status_code == 200
    assert decorrido < 2.0, f"webhook levou {decorrido:.2f}s para responder (RNF-13: < 2s)"


def test_falha_no_processamento_em_segundo_plano_nao_vira_erro_na_confirmacao() -> None:
    async def handler_com_falha(message: ChannelMessage) -> str | None:
        raise RuntimeError("falha simulada no processamento")

    app = _app_de_teste(handler_com_falha)

    with TestClient(app) as client:
        resposta = client.post(
            f"/webhook/telegram/{_SECRET}",
            json=_update_de_texto(),
            headers={_HEADER: _SECRET},
        )

    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}


def test_com_telegram_mode_polling_a_rota_do_webhook_nao_existe() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:pass@localhost/db",
        google_api_key="fake-key-de-teste",
        telegram_mode="polling",
    )
    app = create_app(settings=settings)

    with TestClient(app) as client:
        resposta = client.post(f"/webhook/telegram/{_SECRET}", json=_update_de_texto())

    assert resposta.status_code == 404
