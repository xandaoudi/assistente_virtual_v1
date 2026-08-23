"""T3.3 — com FunctionModel, uma tool chamada opera sobre o usuário das Deps, não outro."""

import uuid
from datetime import date

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.adapters.agent import Deps, create_agent, to_tool_context
from app.domain.enums import TransactionType
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ToolSuccess
from app.tools.schemas import CreateTransactionParams, GetSummaryParams

pytestmark = pytest.mark.e2e

_HOJE = date(2026, 8, 23)


def _ctx(user_id: uuid.UUID) -> ToolContext:
    return ToolContext(user_id=user_id, timezone="America/Sao_Paulo", currency="BRL", today=_HOJE)


def _chamar_get_summary(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="get_summary",
                    args={"params": {"start_date": str(_HOJE), "end_date": str(_HOJE)}},
                )
            ]
        )
    return ModelResponse(parts=[TextPart(content="resumo entregue")])


@pytest.mark.asyncio
async def test_tool_chamada_opera_sobre_o_usuario_das_deps_nao_outro() -> None:
    registry = ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )
    usuario_a = uuid.uuid4()
    usuario_b = uuid.uuid4()

    await registry.create_transaction(
        _ctx(usuario_a),
        CreateTransactionParams(
            type=TransactionType.EXPENSE, amount="100,00", description="Mercado"
        ),
    )
    await registry.create_transaction(
        _ctx(usuario_b),
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="999,00", description="Outro"),
    )

    agent = create_agent(model=FunctionModel(_chamar_get_summary))

    @agent.tool
    async def get_summary(ctx: RunContext[Deps], params: GetSummaryParams) -> str:
        resultado = await ctx.deps.tools.get_summary(to_tool_context(ctx.deps), params)
        assert isinstance(resultado, ToolSuccess)
        return str(resultado.data.total_expenses)

    deps_usuario_a = Deps(
        user_id=usuario_a,
        timezone="America/Sao_Paulo",
        currency="BRL",
        today=_HOJE,
        tools=registry,
    )

    result = await agent.run("quanto gastei hoje?", deps=deps_usuario_a)

    tool_return = next(
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    )
    assert tool_return.content == "100.00"
    assert result.output == "resumo entregue"
