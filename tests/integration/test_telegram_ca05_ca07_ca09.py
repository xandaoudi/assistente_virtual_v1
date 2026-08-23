"""T3.14 — prova automatizada do roteiro de saída da Etapa 3, sobre o webhook real e
Postgres de verdade: CA-05 (registrar despesa), CA-07 (resumo do mês), CA-09 (follow-up),
RF-70 (recusa fora de escopo) e idempotência (T2.11) entre os cinco passos.

A verificação manual no Telegram real (roteiro documentado em `docs/roteiro_manual_t3_14.md`)
prova que funciona hoje; este teste é o que impede alguém de quebrar isso depois. As duas são
necessárias — RNF-35 é explícito: um `FunctionModel` aqui prova a fiação (schema -> tool ->
domínio -> banco -> webhook -> resposta), não que o Gemini entende português (isso é a T3.13).
"""

import asyncio
import calendar
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.channel_message import ChannelMessage
from app.adapters.production import build_production_pipeline
from app.api.telegram_webhook import build_telegram_webhook_router
from app.core.db import get_session_maker
from app.models.user import User
from app.repositories.sqlalchemy import (
    SqlAlchemyTransactionRepository,
    SqlAlchemyUserChannelRepository,
)
from app.tools.schemas import CreateTransactionResult, GetSummaryResult

pytestmark = pytest.mark.integration

_SECRET = "segredo-ca05-ca07-ca09"
_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_CHAT_ID = "424242"

# "Hoje" no mesmo fuso que a produção usa (T3.8: usuário novo nasce em America/Sao_Paulo) —
# não o fuso da máquina local, senão a data do passo 1 diverge da que o webhook calcula.
_HOJE = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
_ONTEM = _HOJE - timedelta(days=1)
_INICIO_MES = _HOJE.replace(day=1)
_FIM_MES = _HOJE.replace(day=calendar.monthrange(_HOJE.year, _HOJE.month)[1])
_ULTIMO_DIA_MES_PASSADO = _INICIO_MES - timedelta(days=1)
_INICIO_MES_PASSADO = _ULTIMO_DIA_MES_PASSADO.replace(day=1)
_FIM_MES_PASSADO = _ULTIMO_DIA_MES_PASSADO

_TEXTO_PASSO_1 = "gastei 45 no mercado ontem"
_TEXTO_PASSO_2 = "quanto gastei esse mês?"
_TEXTO_PASSO_3 = "e no mês passado?"
_TEXTO_PASSO_4 = "qual a capital da França?"
_RECUSA_ESCOPO = "Isso foge do meu escopo — posso ajudar com finanças e agenda!"


def _texto_do_ultimo_pedido_do_usuario(messages: list[ModelMessage]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return None


def _ultimo_retorno_de_tool(messages: list[ModelMessage]) -> ToolReturnPart | None:
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart):
                return part
    return None


def _decide_chamada(texto: str) -> ModelResponse:
    if "frança" in texto.lower():
        return ModelResponse(parts=[TextPart(content=_RECUSA_ESCOPO)])
    if "mês passado" in texto.lower():
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="get_summary",
                    args={
                        "params": {
                            "start_date": str(_INICIO_MES_PASSADO),
                            "end_date": str(_FIM_MES_PASSADO),
                        }
                    },
                )
            ]
        )
    if "esse mês" in texto.lower():
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="get_summary",
                    args={"params": {"start_date": str(_INICIO_MES), "end_date": str(_FIM_MES)}},
                )
            ]
        )
    if "gastei 45 no mercado ontem" in texto.lower():
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="create_transaction",
                    args={
                        "params": {
                            "type": "expense",
                            "amount": "45,00",
                            "description": "Mercado",
                            "date": str(_ONTEM),
                            "category": "Mercado",
                        }
                    },
                )
            ]
        )
    return ModelResponse(parts=[TextPart(content="Não entendi.")])


def _resposta_para_o_retorno_de_tool(retorno: ToolReturnPart) -> ModelResponse:
    resultado = retorno.content
    if isinstance(resultado, CreateTransactionResult):
        texto = f"Registrei R$ {resultado.amount} no {resultado.category}, em {resultado.date}."
    elif isinstance(resultado, GetSummaryResult):
        texto = f"Você gastou R$ {resultado.total_expenses} no período."
    else:
        texto = "Feito."
    return ModelResponse(parts=[TextPart(content=texto)])


chamadas_do_roteiro: list[list[ModelMessage]] = []


def _roteiro(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    chamadas_do_roteiro.append(list(messages))

    retorno = _ultimo_retorno_de_tool(messages)
    ultima_mensagem = messages[-1]
    # Um ToolReturnPart só é a "última coisa que aconteceu" quando está na mensagem mais
    # recente — sem isso, o passo seguinte (que não chama tool nenhuma) acharia por engano
    # que ainda está respondendo a uma tool de um turno anterior.
    if retorno is not None and any(
        isinstance(part, ToolReturnPart) for part in ultima_mensagem.parts
    ):
        return _resposta_para_o_retorno_de_tool(retorno)

    texto = _texto_do_ultimo_pedido_do_usuario(messages)
    if texto is None:
        return ModelResponse(parts=[TextPart(content="Não entendi.")])
    return _decide_chamada(texto)


class _SenderCaptura:
    def __init__(self) -> None:
        self.mensagens: list[tuple[str, str]] = []

    async def send_chat_action(self, chat_id: str, action: str) -> None:
        pass

    async def send_message(self, chat_id: str, text: str) -> None:
        self.mensagens.append((chat_id, text))


def _update(update_id: int, message_id: int, texto: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "chat": {"id": int(_CHAT_ID), "type": "private"},
            "date": 1735000000,
            "text": texto,
        },
    }


async def _remover_usuario_por_chat_id(chat_id: str) -> None:
    user_id = await SqlAlchemyUserChannelRepository().get_user_id("telegram", chat_id)
    if user_id is None:
        return
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)  # ON DELETE CASCADE remove tudo que pertence a ele
            await session.commit()


@pytest.mark.asyncio
async def test_roteiro_ca05_ca07_ca09_e_idempotencia_no_webhook_com_postgres_real() -> None:
    chamadas_do_roteiro.clear()
    handler_real = build_production_pipeline(max_history_messages=20, model=FunctionModel(_roteiro))
    concluido = asyncio.Event()

    async def handler(message: ChannelMessage) -> str | None:
        resultado = await handler_real(message)
        concluido.set()
        return resultado

    sender = _SenderCaptura()
    app = FastAPI()
    app.include_router(
        build_telegram_webhook_router(
            webhook_secret=_SECRET, handler=handler, telegram_client=sender
        )
    )
    transport = httpx.ASGITransport(app=app)

    async def _envia(update_id: int, message_id: int, texto: str) -> None:
        concluido.clear()
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resposta = await client.post(
                f"/webhook/telegram/{_SECRET}",
                json=_update(update_id, message_id, texto),
                headers={_HEADER: _SECRET},
            )
            assert resposta.status_code == 200
        await asyncio.wait_for(concluido.wait(), timeout=10.0)

    try:
        # Passo 1 (CA-05): confirma o registro; banco tem despesa de R$ 45,00, ontem, Mercado.
        await _envia(1, 1, _TEXTO_PASSO_1)
        assert "45" in sender.mensagens[-1][1]

        user_id = await SqlAlchemyUserChannelRepository().get_user_id("telegram", _CHAT_ID)
        assert user_id is not None
        transacoes_repo = SqlAlchemyTransactionRepository()
        persistidas = await transacoes_repo.list_by_user(user_id)
        assert len(persistidas) == 1
        assert persistidas[0].amount == Decimal("45.00")
        assert persistidas[0].date == _ONTEM
        assert str(persistidas[0].type.value) == "expense"

        # Passo 2 (CA-07): total correto do mês corrente.
        await _envia(2, 2, _TEXTO_PASSO_2)
        assert "45" in sender.mensagens[-1][1]

        # Passo 3 (CA-09): "e no mês passado?" é entendido como follow-up do passo 2.
        await _envia(3, 3, _TEXTO_PASSO_3)
        assert "0" in sender.mensagens[-1][1]  # nenhuma transação no mês passado

        turno_3 = next(
            chamada
            for chamada in chamadas_do_roteiro
            if _texto_do_ultimo_pedido_do_usuario(chamada) == _TEXTO_PASSO_3
        )
        assert any(
            isinstance(part, UserPromptPart) and part.content == _TEXTO_PASSO_2
            for message in turno_3
            for part in message.parts
        ), "histórico do passo 2 não chegou ao passo 3 — CA-09 não foi provado"

        # Passo 4 (RF-70): recusa educada, redireciona ao escopo, nenhuma tool chamada.
        await _envia(4, 4, _TEXTO_PASSO_4)
        resposta_passo_4 = sender.mensagens[-1][1].lower()
        assert "escopo" in resposta_passo_4
        assert "frança" not in resposta_passo_4 and "paris" not in resposta_passo_4
        assert len(await transacoes_repo.list_by_user(user_id)) == 1

        # Passo 5: mesma mensagem do passo 1, mesmo message_id — não duplica a despesa.
        await _envia(5, 1, _TEXTO_PASSO_1)
        persistidas_final = await transacoes_repo.list_by_user(user_id)
        assert len(persistidas_final) == 1
        assert persistidas_final[0].id == persistidas[0].id
    finally:
        await _remover_usuario_por_chat_id(_CHAT_ID)
