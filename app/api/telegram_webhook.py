"""Webhook do Telegram (T3.7) — resolve a tensão RNF-13 x RNF-12.

A rota confirma o recebimento *antes* de qualquer processamento (RNF-13: responder em até
2s) e processa em segundo plano — via `asyncio.create_task`, não `BackgroundTasks` do
FastAPI, para que a resposta não espere o processamento nem sob o test client. Uma falha
no processamento em segundo plano nunca vira erro na confirmação: ela já foi enviada.
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.adapters.channel_message import ChannelMessage
from app.adapters.telegram import TelegramSender, handle_and_reply, parse_telegram_update

MessageHandler = Callable[[ChannelMessage], Awaitable[str | None]]

_tarefas_em_andamento: set[asyncio.Task[None]] = set()


def _agendar(coro: Coroutine[Any, Any, None]) -> None:
    """`create_task` com referência mantida — sem isso a tarefa pode ser coletada pelo GC
    no meio da execução, um problema conhecido do asyncio."""
    tarefa = asyncio.create_task(coro)
    _tarefas_em_andamento.add(tarefa)
    tarefa.add_done_callback(_tarefas_em_andamento.discard)


async def _processar_em_segundo_plano(
    update: object,
    handler: MessageHandler,
    telegram_client: TelegramSender,
) -> None:
    """A confirmação ao Telegram já foi enviada antes deste laço começar — por isso
    `handle_and_reply` cuida de nunca deixar uma falha propagar daqui pra fora."""
    mensagem = parse_telegram_update(update)
    if mensagem is None:
        return
    await handle_and_reply(mensagem, handler, telegram_client)


def build_telegram_webhook_router(
    *,
    webhook_secret: str,
    handler: MessageHandler,
    telegram_client: TelegramSender,
) -> APIRouter:
    router = APIRouter()

    @router.post(f"/webhook/telegram/{webhook_secret}")
    async def receive_telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if x_telegram_bot_api_secret_token != webhook_secret:
            raise HTTPException(status_code=401, detail="token secreto inválido ou ausente")

        try:
            update = await request.json()
        except ValueError:
            update = None

        _agendar(_processar_em_segundo_plano(update, handler, telegram_client))
        return {"ok": True}

    return router
