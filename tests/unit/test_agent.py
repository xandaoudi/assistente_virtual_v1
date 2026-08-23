"""Deps do agente e a tradução para ToolContext — CA-13 no nível do schema real (T3.3)."""

import asyncio
import json
import uuid
from datetime import date

import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel

from app.adapters.agent import Deps, create_agent, to_tool_context
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import CreateTransactionParams, GetSummaryParams

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 23)


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


def _deps(user_id: uuid.UUID | None = None, idempotency_key: str | None = None) -> Deps:
    return Deps(
        user_id=user_id or uuid.uuid4(),
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=_novo_registry(),
        idempotency_key=idempotency_key,
    )


def test_to_tool_context_traduz_todos_os_campos_de_deps() -> None:
    deps = _deps(idempotency_key="chave-123")

    ctx = to_tool_context(deps)

    assert ctx.user_id == deps.user_id
    assert ctx.timezone == deps.timezone
    assert ctx.currency == deps.currency
    assert ctx.today == deps.today
    assert ctx.idempotency_key == "chave-123"


def test_agent_e_tipado_com_deps() -> None:
    agent = create_agent(model=TestModel())

    assert agent.deps_type is Deps


@pytest.mark.asyncio
async def test_nenhum_schema_enviado_ao_modelo_contem_user_id() -> None:
    agent = create_agent(model=TestModel(call_tools=[]))

    @agent.tool
    async def create_transaction(ctx: RunContext[Deps], params: CreateTransactionParams) -> str:
        return "não executado neste teste"

    @agent.tool
    async def get_summary(ctx: RunContext[Deps], params: GetSummaryParams) -> str:
        return "não executado neste teste"

    await agent.run("oi", deps=_deps())

    tool_defs = agent.model.last_model_request_parameters.function_tools  # type: ignore[union-attr]
    assert tool_defs, "nenhuma tool foi registrada no agente — teste não prova nada"
    for tool_def in tool_defs:
        schema_serializado = json.dumps(tool_def.parameters_json_schema)
        assert "user_id" not in schema_serializado, f"{tool_def.name}: schema expõe user_id"


@pytest.mark.asyncio
async def test_deteccao_de_user_id_no_schema_realmente_funciona() -> None:
    # Prova que o teste acima não é vazio: uma tool que aceitasse user_id seria pega.
    agent = create_agent(model=TestModel(call_tools=[]))

    @agent.tool
    async def tool_com_vazamento(ctx: RunContext[Deps], user_id: str) -> str:
        return user_id

    await agent.run("oi", deps=_deps())

    tool_defs = agent.model.last_model_request_parameters.function_tools  # type: ignore[union-attr]
    schema_serializado = json.dumps(tool_defs[0].parameters_json_schema)
    assert "user_id" in schema_serializado


@pytest.mark.asyncio
async def test_tools_recebem_o_user_id_correto_vindo_das_deps() -> None:
    capturado: list[uuid.UUID] = []
    agent = create_agent(model=TestModel())

    @agent.tool
    async def tool_de_teste(ctx: RunContext[Deps]) -> str:
        capturado.append(ctx.deps.user_id)
        return "ok"

    deps = _deps()
    await agent.run("oi", deps=deps)

    assert capturado == [deps.user_id]


@pytest.mark.asyncio
async def test_dois_agentes_com_deps_diferentes_nao_cruzam_identidade() -> None:
    capturado: dict[str, uuid.UUID] = {}
    agent = create_agent(model=TestModel())

    @agent.tool
    async def tool_de_teste(ctx: RunContext[Deps]) -> str:
        capturado[str(ctx.deps.user_id)] = ctx.deps.user_id
        return "ok"

    deps_a = _deps()
    deps_b = _deps()
    assert deps_a.user_id != deps_b.user_id

    await asyncio.gather(
        agent.run("oi", deps=deps_a),
        agent.run("oi", deps=deps_b),
    )

    assert set(capturado.values()) == {deps_a.user_id, deps_b.user_id}
