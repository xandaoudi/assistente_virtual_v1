"""T3.14 — envio de resposta compartilhado entre webhook (T3.7) e poller: resposta padrão
quando o handler não devolve nada, formatação e divisão antes de mandar pro Telegram."""

from datetime import UTC, datetime

import pytest

from app.adapters.channel_message import ChannelMessage
from app.adapters.telegram import (
    UNSUPPORTED_CONTENT_REPLY,
    format_telegram_output,
    handle_and_reply,
    send_reply,
)

pytestmark = pytest.mark.unit


class _TelegramSenderFalso:
    def __init__(self) -> None:
        self.mensagens_enviadas: list[tuple[str, str]] = []
        self.chat_actions: list[tuple[str, str]] = []

    async def send_chat_action(self, chat_id: str, action: str) -> None:
        self.chat_actions.append((chat_id, action))

    async def send_message(self, chat_id: str, text: str) -> None:
        self.mensagens_enviadas.append((chat_id, text))


def _mensagem(texto: str | None = "oi") -> ChannelMessage:
    return ChannelMessage(
        channel="telegram",
        external_user_id="555",
        text=texto,
        media=None,
        timestamp=datetime.fromtimestamp(1735000000, tz=UTC),
        message_id="1",
    )


@pytest.mark.asyncio
async def test_envia_a_resposta_do_handler_formatada() -> None:
    sender = _TelegramSenderFalso()

    await send_reply(sender, _mensagem(), "Registrei **R$ 45,00** no mercado.")

    assert sender.mensagens_enviadas == [("555", "Registrei *R$ 45,00* no mercado\\.")]


@pytest.mark.asyncio
async def test_resposta_none_usa_a_resposta_padrao_do_canal() -> None:
    sender = _TelegramSenderFalso()

    await send_reply(sender, _mensagem(texto=None), None)

    assert sender.mensagens_enviadas == [("555", format_telegram_output(UNSUPPORTED_CONTENT_REPLY))]


@pytest.mark.asyncio
async def test_sem_resposta_alguma_nao_envia_nada() -> None:
    sender = _TelegramSenderFalso()

    await send_reply(sender, _mensagem(texto="oi"), None)

    assert sender.mensagens_enviadas == []


@pytest.mark.asyncio
async def test_resposta_longa_e_dividida_em_varias_mensagens() -> None:
    sender = _TelegramSenderFalso()

    await send_reply(sender, _mensagem(), "a" * 5000)

    assert len(sender.mensagens_enviadas) == 2
    assert all(chat_id == "555" for chat_id, _ in sender.mensagens_enviadas)


@pytest.mark.asyncio
async def test_handle_and_reply_manda_digitando_roda_o_handler_e_envia_a_resposta() -> None:
    sender = _TelegramSenderFalso()

    async def handler(message: ChannelMessage) -> str | None:
        return "Registrado."

    await handle_and_reply(_mensagem(), handler, sender)

    assert sender.chat_actions == [("555", "typing")]
    assert sender.mensagens_enviadas == [("555", "Registrado\\.")]


@pytest.mark.asyncio
async def test_handle_and_reply_falha_no_handler_nunca_propaga() -> None:
    sender = _TelegramSenderFalso()

    async def handler_com_falha(message: ChannelMessage) -> str | None:
        raise RuntimeError("falha simulada")

    # Não deve levantar — uma falha aqui nunca pode derrubar o poller nem o webhook.
    await handle_and_reply(_mensagem(), handler_com_falha, sender)

    assert sender.mensagens_enviadas == []


@pytest.mark.asyncio
async def test_handle_and_reply_falha_no_indicador_de_digitando_nao_impede_a_resposta() -> None:
    sender = _TelegramSenderFalso()

    async def falha_digitando(chat_id: str, action: str) -> None:
        raise RuntimeError("indicador falhou")

    sender.send_chat_action = falha_digitando  # type: ignore[method-assign]

    async def handler(message: ChannelMessage) -> str | None:
        return "Registrado."

    await handle_and_reply(_mensagem(), handler, sender)

    assert sender.mensagens_enviadas == [("555", "Registrado\\.")]
