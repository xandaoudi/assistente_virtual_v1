"""Envelope de resultado das tools e catálogo de erros (RF-87, RF-71).

Toda tool devolve `ToolResult`, nunca deixa uma exceção escapar. `run_safely` é o único
ponto por onde uma chamada de domínio passa antes de virar resposta — é aqui que uma
exceção inesperada é convertida, sem vazar stack trace, nome de tabela ou detalhe interno.
"""

from collections.abc import Awaitable
from dataclasses import dataclass
from enum import StrEnum

from app.domain.errors import DomainError

_MENSAGEM_ERRO_INTERNO = "Erro interno inesperado. Tente novamente mais tarde."


class ErrorCode(StrEnum):
    """Catálogo mínimo de códigos de erro devolvidos por uma tool."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    CONFLICT = "CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ToolSuccess[T]:
    data: T


@dataclass(frozen=True)
class ToolError:
    """`detail` é opcional e só carrega informação já segura para o modelo ver."""

    code: ErrorCode
    message: str
    detail: dict[str, object] | None = None


type ToolResult[T] = ToolSuccess[T] | ToolError


async def run_safely[T](coro: Awaitable[T]) -> ToolResult[T]:
    """Executa uma chamada de domínio e converte qualquer exceção no envelope de erro.

    `DomainError` vira `BUSINESS_RULE_VIOLATION` com a própria mensagem — já escrita para
    o usuário final. Qualquer outra exceção vira `INTERNAL_ERROR` com mensagem genérica:
    a mensagem original nunca é repassada, porque pode conter detalhe de implementação
    (stack trace, nome de tabela, id interno — RF-71).
    """
    try:
        return ToolSuccess(data=await coro)
    except DomainError as exc:
        return ToolError(code=ErrorCode.BUSINESS_RULE_VIOLATION, message=str(exc))
    except Exception:
        return ToolError(code=ErrorCode.INTERNAL_ERROR, message=_MENSAGEM_ERRO_INTERNO)
