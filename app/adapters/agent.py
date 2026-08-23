"""Agente Pydantic AI com `Deps` tipadas (§3.3.3, RNF-04, CA-13).

`Deps` carrega tudo que uma execução do agente sabe sobre quem está chamando. O `user_id`
chega aqui resolvido do lado do servidor (T3.8) e nunca entra no schema visto pela LLM: as
tools recebem `RunContext[Deps]`, não um parâmetro `user_id`. `to_tool_context` traduz
`Deps` para o `ToolContext` que as tools da Etapa 2 já esperam — o desenho pesado foi feito
lá (T2.2), aqui é só tradução.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.adapters.llm import build_llm_model
from app.adapters.prompts import load_system_prompt
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class Deps:
    """Imutável: duas execuções do agente nunca compartilham estado através do mesmo Deps."""

    user_id: uuid.UUID
    timezone: str
    currency: str
    today: date
    tools: ToolRegistry
    idempotency_key: str | None = None


def to_tool_context(deps: Deps) -> ToolContext:
    return ToolContext(
        user_id=deps.user_id,
        timezone=deps.timezone,
        currency=deps.currency,
        today=deps.today,
        idempotency_key=deps.idempotency_key,
    )


def create_agent(model: Model | None = None) -> Agent[Deps, str]:
    # `instructions=`, não `system_prompt=`: o `system_prompt` só é gravado na primeira
    # mensagem da história e nunca é reinjetado quando `agent.run(message_history=...)`
    # já tem conteúdo — e a T3.5 (RNF-06) tira de propósito qualquer `SystemPromptPart`
    # vindo do histórico recarregado. O resultado, com `system_prompt=`, era um agente sem
    # instrução nenhuma a partir do segundo turno de qualquer conversa (bug real encontrado
    # na verificação manual da T3.14). `instructions=` é recalculado a cada chamada ao
    # modelo, nunca depende do que foi persistido.
    return Agent(
        model or build_llm_model(),
        deps_type=Deps,
        instructions=load_system_prompt(),
    )
