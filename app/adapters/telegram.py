"""Adapter do Telegram (T3.6, RNF-10): conversão de/para `ChannelMessage` e o poller.

Ninguém fora deste módulo (e de `app.telegram_poller`) sabe que existe um `Update` do
Telegram — domain, tools e o núcleo do agente falam só `ChannelMessage` (testado em
`tests/unit/test_architecture.py`).

Os dois modos de recepção (polling e webhook, T3.6/T3.7) compartilham `parse_telegram_update`:
a `getUpdates` do polling devolve um array do mesmo objeto `Update` que o webhook recebe um
de cada vez no corpo do POST — não há dois caminhos de conversão, só duas portas de entrada.
"""

import asyncio
import math
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from app.adapters.channel_message import ChannelMessage

TELEGRAM_MESSAGE_LIMIT = 4096

UNSUPPORTED_CONTENT_REPLY = (
    "Por enquanto eu só entendo texto — descreva o gasto ou compromisso em palavras que "
    "eu registro certinho."
)

_MEDIA_KEYS = (
    "photo",
    "sticker",
    "voice",
    "video",
    "video_note",
    "document",
    "audio",
    "animation",
)


def parse_telegram_update(update: object) -> ChannelMessage | None:
    """Converte um `Update` do Telegram em `ChannelMessage`. Nunca levanta — entrada não
    confiável (vem da rede) que só produz `None` quando não dá para interpretar."""
    if not isinstance(update, dict):
        return None

    message = update.get("message")
    if not isinstance(message, dict):
        message = update.get("edited_message")
    if not isinstance(message, dict):
        return None

    update_id = update.get("update_id")
    chat = message.get("chat")
    message_id = message.get("message_id")
    date = message.get("date")

    if not isinstance(update_id, int) or not isinstance(chat, dict):
        return None
    chat_id = chat.get("id")
    if not isinstance(chat_id, int) or not isinstance(message_id, int):
        return None

    try:
        timestamp = datetime.fromtimestamp(int(date), tz=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

    texto = message.get("text")
    if not isinstance(texto, str):
        legenda = message.get("caption")
        texto = legenda if isinstance(legenda, str) else None

    media = next((chave for chave in _MEDIA_KEYS if chave in message), None)

    return ChannelMessage(
        channel="telegram",
        external_user_id=str(chat_id),
        text=texto,
        media=media,
        timestamp=timestamp,
        message_id=str(message_id),
    )


def default_reply_for(message: ChannelMessage) -> str | None:
    """Resposta educada quando não há texto para processar (figurinha, foto sem legenda)."""
    if message.text is None:
        return UNSUPPORTED_CONTENT_REPLY
    return None


def extract_updates_from_poll_response(response: dict[str, object]) -> list[dict[str, object]]:
    resultado = response.get("result")
    if not isinstance(resultado, list):
        return []
    return [item for item in resultado if isinstance(item, dict)]


_MARKDOWN_V2_ESCAPADOS = re.escape("_*[]()~`>#+-=|{}.!\\")
_PADRAO_NEGRITO = re.compile(r"\*\*(.+?)\*\*")


def _escapar_markdown_v2(texto: str) -> str:
    return re.sub(f"([{_MARKDOWN_V2_ESCAPADOS}])", r"\\\1", texto)


def format_telegram_output(text: str) -> str:
    """Escapa a resposta para MarkdownV2 e traduz `**negrito**` para a sintaxe do Telegram."""
    partes: list[str] = []
    fim_do_ultimo_trecho = 0
    for match in _PADRAO_NEGRITO.finditer(text):
        partes.append(_escapar_markdown_v2(text[fim_do_ultimo_trecho : match.start()]))
        partes.append(f"*{_escapar_markdown_v2(match.group(1))}*")
        fim_do_ultimo_trecho = match.end()
    partes.append(_escapar_markdown_v2(text[fim_do_ultimo_trecho:]))
    return "".join(partes)


def split_telegram_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Divide em partes que cabem no limite do Telegram, preferindo cortar em quebra de linha."""
    if len(text) <= limit:
        return [text]

    partes: list[str] = []
    restante = text
    while len(restante) > limit:
        corte = restante.rfind("\n", 0, limit)
        if corte <= 0:
            corte = restante.rfind(" ", 0, limit)
        if corte <= 0:
            corte = limit
        partes.append(restante[:corte])
        restante = restante[corte:].lstrip("\n ")
    if restante:
        partes.append(restante)
    return partes


class TelegramApiError(Exception):
    """Falha de rede ou HTTP ao chamar a Bot API do Telegram."""


class TelegramUpdateSource(Protocol):
    async def get_updates(self, offset: int) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class PollResult:
    messages: list[ChannelMessage]
    next_offset: int


async def poll_once(source: TelegramUpdateSource, offset: int) -> PollResult:
    updates = await source.get_updates(offset)
    mensagens: list[ChannelMessage] = []
    proximo_offset = offset
    for update in updates:
        update_id = update.get("update_id") if isinstance(update, dict) else None
        if isinstance(update_id, int):
            proximo_offset = max(proximo_offset, update_id + 1)
        mensagem = parse_telegram_update(update)
        if mensagem is not None:
            mensagens.append(mensagem)
    return PollResult(messages=mensagens, next_offset=proximo_offset)


_BACKOFF_INICIAL_SEGUNDOS = 1.0
_BACKOFF_MAXIMO_SEGUNDOS = 30.0


async def run_polling_loop(
    source: TelegramUpdateSource,
    handler: Callable[[ChannelMessage], Awaitable[None]],
    *,
    initial_offset: int = 0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    should_continue: Callable[[], bool] = lambda: True,
) -> None:
    """Laço de longa duração do `getUpdates` — roda em processo próprio (`app.telegram_poller`).

    Uma queda de rede nunca derruba o laço: espera com backoff exponencial e tenta de novo.
    """
    offset = initial_offset
    espera = _BACKOFF_INICIAL_SEGUNDOS
    while should_continue():
        try:
            resultado = await poll_once(source, offset)
        except TelegramApiError:
            await sleep(espera)
            espera = min(espera * 2, _BACKOFF_MAXIMO_SEGUNDOS)
            continue

        espera = _BACKOFF_INICIAL_SEGUNDOS
        offset = resultado.next_offset
        for mensagem in resultado.messages:
            await handler(mensagem)


class HttpTelegramUpdateSource:
    """`TelegramUpdateSource` real, sobre a Bot API — usado só pelo `app.telegram_poller`."""

    def __init__(self, bot_token: str, *, timeout_seconds: float = 30.0) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._timeout_seconds = timeout_seconds

    async def get_updates(self, offset: int) -> list[dict[str, object]]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds + 10) as client:
                resposta = await client.get(
                    f"{self._base_url}/getUpdates",
                    params={"offset": offset, "timeout": math.floor(self._timeout_seconds)},
                )
                resposta.raise_for_status()
        except httpx.HTTPError as exc:
            raise TelegramApiError(str(exc)) from exc

        corpo = resposta.json()
        if not isinstance(corpo, dict) or not corpo.get("ok"):
            raise TelegramApiError(f"resposta inesperada da Bot API: {corpo!r}")
        return extract_updates_from_poll_response(corpo)


class TelegramSender(Protocol):
    """O que o webhook (T3.7) precisa para responder — dublado nos testes (RNF-39)."""

    async def send_chat_action(self, chat_id: str, action: str) -> None: ...

    async def send_message(self, chat_id: str, text: str) -> None: ...


class TelegramClient:
    """`TelegramSender` real, sobre a Bot API.

    `send_message` envia `text` como uma única mensagem, já formatada e dentro do limite —
    é responsabilidade de quem chama aplicar `format_telegram_output`/`split_telegram_message`
    antes (`app.api.telegram_webhook`), para que um `TelegramSender` dublado nos testes veja
    exatamente o que seria enviado de verdade.
    """

    def __init__(self, bot_token: str, *, timeout_seconds: float = 10.0) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._timeout_seconds = timeout_seconds

    async def send_chat_action(self, chat_id: str, action: str) -> None:
        await self._post("sendChatAction", {"chat_id": chat_id, "action": action})

    async def send_message(self, chat_id: str, text: str) -> None:
        await self._post(
            "sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"}
        )

    async def _post(self, metodo: str, payload: dict[str, object]) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                resposta = await client.post(f"{self._base_url}/{metodo}", json=payload)
                resposta.raise_for_status()
        except httpx.HTTPError as exc:
            raise TelegramApiError(str(exc)) from exc
