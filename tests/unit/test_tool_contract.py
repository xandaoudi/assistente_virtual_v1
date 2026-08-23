"""Prova formal do CA-13 e do CA-14 (T2.13) — critérios de aceite da Etapa 2.

Os três testes de completude (schema de entrada, envelope de saída, wrapper de
auditoria) percorrem o `ToolRegistry` por introspecção: uma tool nova adicionada fora
do padrão reprova o build automaticamente, sem que alguém precise lembrar de escrever
um teste para ela.
"""

import ast
import inspect
import typing
import uuid
from collections.abc import Callable, Coroutine
from datetime import date
from pathlib import Path
from typing import Any

import pydantic_ai.models
import pytest
from pydantic import BaseModel

from app.domain.enums import TransactionType
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)
from app.tools.context import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.results import ToolResult, ToolSuccess
from app.tools.schemas import (
    CreateTransactionParams,
    GetSummaryParams,
    ResolveRelativeDateParams,
    ToolParams,
)

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_HOJE = date(2026, 8, 21)


def _todas_as_subclasses(cls: type[BaseModel]) -> set[type[BaseModel]]:
    diretas = set(cls.__subclasses__())
    return diretas | {neta for sub in diretas for neta in _todas_as_subclasses(sub)}


def _metodos_publicos_de_tool(
    registry_cls: type = ToolRegistry,
) -> list[tuple[str, Callable[..., Coroutine[Any, Any, Any]]]]:
    return [
        (nome, metodo)
        for nome, metodo in inspect.getmembers(registry_cls, predicate=inspect.iscoroutinefunction)
        if not nome.startswith("_")
    ]


def _novo_registry() -> ToolRegistry:
    return ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


def _novo_contexto() -> ToolContext:
    return ToolContext(
        user_id=uuid.uuid4(), timezone="America/Sao_Paulo", currency="BRL", today=_HOJE
    )


def _importa_pydantic_ai(arquivo: Path) -> bool:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    for node in ast.walk(arvore):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "pydantic_ai" for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.split(".")[0] == "pydantic_ai"
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# CA-13 — user_id nunca é parâmetro visível à LLM (RNF-04)
# ---------------------------------------------------------------------------


def test_ca13_nenhum_schema_de_tool_tem_campo_user_id() -> None:
    for schema in _todas_as_subclasses(ToolParams):
        assert "user_id" not in schema.model_fields, schema.__name__


def test_ca13_todo_schema_de_tool_rejeita_campo_extra() -> None:
    # extra="forbid" garante que um eventual "user_id" solto — não declarado no schema —
    # também é rejeitado na validação, não silenciosamente ignorado.
    for schema in _todas_as_subclasses(ToolParams):
        assert schema.model_config.get("extra") == "forbid", schema.__name__


# ---------------------------------------------------------------------------
# CA-14 — a suíte de tools roda inteira sem nenhuma chamada a LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ca14_tools_executam_sem_nenhuma_chamada_a_llm() -> None:
    # A trava global (tests/conftest.py) já impede qualquer chamada real à LLM durante
    # toda a sessão de testes; aqui, chamar tools de verdade prova que elas nem tentam.
    assert pydantic_ai.models.ALLOW_MODEL_REQUESTS is False

    registry = _novo_registry()
    ctx = _novo_contexto()

    criada = await registry.create_transaction(
        ctx,
        CreateTransactionParams(type=TransactionType.EXPENSE, amount="10,00", description="Café"),
    )
    resumo = await registry.get_summary(ctx, GetSummaryParams(start_date=_HOJE, end_date=_HOJE))
    periodo = await registry.resolve_relative_date(
        ctx, ResolveRelativeDateParams(expression="hoje")
    )

    assert isinstance(criada, ToolSuccess)
    assert isinstance(resumo, ToolSuccess)
    assert isinstance(periodo, ToolSuccess)


def test_nenhum_modulo_de_app_tools_importa_pydantic_ai() -> None:
    # Segunda barreira além do Ruff (mesmo mecanismo de T0.9/RF-86), dedicada aqui à
    # camada de tools especificamente — redundante com test_architecture.py de propósito.
    diretorio = PROJECT_ROOT / "app" / "tools"
    ofensores = [
        str(arquivo.relative_to(PROJECT_ROOT))
        for arquivo in diretorio.rglob("*.py")
        if _importa_pydantic_ai(arquivo)
    ]
    assert ofensores == [], f"RF-86 violado por: {ofensores}"


# ---------------------------------------------------------------------------
# Testes de completude — protegem o padrão para tools futuras, automaticamente
# ---------------------------------------------------------------------------


def test_toda_tool_do_registry_tem_schema_de_entrada_registrado() -> None:
    for nome, metodo in _metodos_publicos_de_tool():
        parametros = list(inspect.signature(metodo).parameters.values())
        assert len(parametros) == 3, f"{nome}: assinatura deveria ser (self, ctx, params)"
        ctx_param, params_param = parametros[1], parametros[2]
        assert ctx_param.annotation is ToolContext, f"{nome}: primeiro parâmetro não é ToolContext"
        assert isinstance(params_param.annotation, type) and issubclass(
            params_param.annotation, ToolParams
        ), f"{nome}: schema de entrada não é um ToolParams: {params_param.annotation!r}"


def test_toda_tool_do_registry_devolve_o_envelope_do_t21() -> None:
    for nome, metodo in _metodos_publicos_de_tool():
        retorno = inspect.signature(metodo).return_annotation
        assert typing.get_origin(retorno) is ToolResult, (
            f"{nome}: retorno não é ToolResult[...] — devolve tipo cru: {retorno!r}"
        )


def test_toda_tool_do_registry_passa_pelo_wrapper_de_auditoria() -> None:
    for nome, metodo in _metodos_publicos_de_tool():
        assert hasattr(metodo, "__wrapped__"), f"{nome}: não passa por @audited (RF-88)"


def test_introspeccao_de_completude_detecta_tool_fora_do_padrao() -> None:
    # Prova que os três testes acima não são vazios: uma "tool" fora do padrão é pega.
    class _RegistryFalso:
        async def tool_sem_padrao(self, ctx: ToolContext, algo: int) -> dict[str, str]:
            return {"nao": "deveria passar"}

    metodos = _metodos_publicos_de_tool(_RegistryFalso)
    assert len(metodos) == 1
    _, metodo = metodos[0]

    retorno = inspect.signature(metodo).return_annotation
    assert typing.get_origin(retorno) is not ToolResult
    assert not hasattr(metodo, "__wrapped__")
