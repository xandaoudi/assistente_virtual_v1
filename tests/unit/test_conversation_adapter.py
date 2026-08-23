"""Serialização do histórico de conversa e higienização ao recarregar (T3.5, RNF-06)."""

from dataclasses import dataclass

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import SystemPromptPart
from pydantic_ai.models.test import TestModel

from app.adapters.conversation import deserialize_messages, serialize_messages

pytestmark = pytest.mark.unit


@dataclass
class _DepsDeTeste:
    pass


@pytest.mark.asyncio
async def test_mensagens_serializam_e_desserializam_sem_perda() -> None:
    agent = Agent(TestModel(), deps_type=_DepsDeTeste)

    @agent.tool
    async def minha_tool(ctx: RunContext[_DepsDeTeste]) -> str:
        return "ok"

    result = await agent.run("gastei 45 no mercado", deps=_DepsDeTeste())
    originais = result.all_messages()

    restauradas = deserialize_messages(serialize_messages(originais))

    assert restauradas == originais


@pytest.mark.asyncio
async def test_serializar_devolve_dicts_json_seguros() -> None:
    # A camada de domínio nunca importa pydantic_ai (RF-86) — o que ela recebe precisa ser
    # dict puro, não um objeto ModelMessage.
    agent = Agent(TestModel())
    result = await agent.run("oi")

    serializadas = serialize_messages(result.all_messages())

    assert isinstance(serializadas, list)
    assert all(isinstance(mensagem, dict) for mensagem in serializadas)


@pytest.mark.asyncio
async def test_higienizacao_remove_system_prompt_gravado_anteriormente() -> None:
    # RNF-06: texto gravado num turno anterior não deve voltar hoje se passando por
    # instrução de sistema. O Pydantic AI garante isso descartando SystemPromptPart ao
    # recarregar de uma fonte que não é o próprio Agent.system_prompt desta execução.
    agent = Agent(TestModel(), system_prompt="Você é um assistente de teste.")
    result = await agent.run("oi")

    serializadas = serialize_messages(result.all_messages())
    assert any(
        part.get("part_kind") == "system-prompt"
        for message in serializadas
        for part in message["parts"]
    ), "o cenário do teste não gravou system prompt algum — teste não prova nada"

    restauradas = deserialize_messages(serializadas)

    assert not any(
        isinstance(part, SystemPromptPart) for message in restauradas for part in message.parts
    )
