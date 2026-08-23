"""Registra as tools do `ToolRegistry` no agente Pydantic AI (T3.4, RF-86).

Percorre `ToolRegistry` por introspecção — a mesma técnica do teste de completude do CA-13
(T2.13) — e registra cada método público como uma tool. Uma tool nova no registry aparece
aqui automaticamente: não existe lista para manter em dia.

`register_tools` não fecha sobre uma instância de `ToolRegistry`: cada chamada resolve
`ctx.deps.tools` em tempo de execução, então o mesmo `Agent` serve qualquer `Deps`.

Envelope do T2.1 -> retorno para o modelo: sucesso devolve só os dados; erro vira
`ToolFailed` com uma mensagem seguro para o usuário (RF-71) — a LLM nunca vê o envelope
cru nem detalhe interno.
"""

import inspect
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ToolFailed

from app.adapters.agent import Deps, to_tool_context
from app.tools.registry import ToolRegistry
from app.tools.results import ErrorCode, ToolError, ToolResult

_MENSAGEM_ERRO_INTERNO = "Erro interno inesperado. Tente novamente mais tarde."

type _RegistryMethod = Callable[..., Coroutine[Any, Any, ToolResult[Any]]]
type _AgentTool = Callable[..., Coroutine[Any, Any, Any]]


def registry_tool_methods(registry_cls: type = ToolRegistry) -> list[tuple[str, _RegistryMethod]]:
    """Todo método público de `registry_cls` — a mesma introspecção usada no CA-13 (T2.13)."""
    return [
        (nome, metodo)
        for nome, metodo in inspect.getmembers(registry_cls, predicate=inspect.iscoroutinefunction)
        if not nome.startswith("_")
    ]


def translate_tool_error(erro: ToolError) -> str:
    """Envelope T2.1 -> texto que o modelo recebe. Nunca repassa detalhe interno (RF-71).

    `INTERNAL_ERROR` sempre vira o texto genérico fixo, ignorando `erro.message` — segunda
    barreira independente do `run_safely` (Etapa 2), caso alguma mensagem vazasse detalhe.
    """
    if erro.code is ErrorCode.INTERNAL_ERROR:
        return _MENSAGEM_ERRO_INTERNO
    if erro.code is ErrorCode.AMBIGUOUS_INPUT:
        return f"{erro.message} Pergunte ao usuário para esclarecer — não adivinhe o valor."
    return erro.message


def _build_tool(nome: str, params_type: type[BaseModel]) -> _AgentTool:
    async def tool(ctx: RunContext[Deps], params: BaseModel) -> Any:
        metodo = getattr(ctx.deps.tools, nome)
        resultado: ToolResult[Any] = await metodo(to_tool_context(ctx.deps), params)
        if isinstance(resultado, ToolError):
            raise ToolFailed(translate_tool_error(resultado))
        return resultado.data

    tool.__name__ = nome
    tool.__annotations__ = {"ctx": RunContext[Deps], "params": params_type, "return": Any}
    return tool


def register_tools(agent: Agent[Deps, str], registry_cls: type = ToolRegistry) -> None:
    for nome, metodo in registry_tool_methods(registry_cls):
        params_type = list(inspect.signature(metodo).parameters.values())[2].annotation
        agent.tool(_build_tool(nome, params_type))
