"""Log de auditoria com redação (RF-88 sem violar o RNF-15).

`redact_params` decide o que é seguro logar. `audited` é o decorador aplicado a toda
função pública do `ToolRegistry`: mede a duração, grava o registro (usuário, tool,
parâmetros redigidos, status, duração) e nunca deixa uma falha de auditoria derrubar a
chamada original — auditoria é observabilidade, não caminho crítico.
"""

import contextlib
import functools
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from app.models.tool_audit_log import ToolAuditLog
from app.tools.context import ToolContext
from app.tools.results import ToolResult, ToolSuccess

_CAMPOS_SENSIVEIS = frozenset({"amount", "min_amount", "max_amount", "description", "query"})
_REDACTED = "[REDACTED]"


def redact_params(params: BaseModel) -> dict[str, object]:
    """Serializa `params` para JSON e substitui todo campo sensível por `"[REDACTED]"`."""
    bruto = params.model_dump(mode="json")
    return {
        chave: (_REDACTED if chave in _CAMPOS_SENSIVEIS else valor)
        for chave, valor in bruto.items()
    }


def audited[P: BaseModel, T](
    tool_name: str,
) -> Callable[
    [Callable[[Any, ToolContext, P], Awaitable[ToolResult[T]]]],
    Callable[[Any, ToolContext, P], Awaitable[ToolResult[T]]],
]:
    def decorator(
        func: Callable[[Any, ToolContext, P], Awaitable[ToolResult[T]]],
    ) -> Callable[[Any, ToolContext, P], Awaitable[ToolResult[T]]]:
        @functools.wraps(func)
        async def wrapper(self: Any, ctx: ToolContext, params: P) -> ToolResult[T]:
            inicio = time.monotonic()
            resultado = await func(self, ctx, params)
            duracao_ms = round((time.monotonic() - inicio) * 1000)
            status = "success" if isinstance(resultado, ToolSuccess) else resultado.code.value

            entry = ToolAuditLog(
                id=uuid.uuid4(),
                user_id=ctx.user_id,
                tool_name=tool_name,
                params=redact_params(params),
                result_status=status,
                duration_ms=duracao_ms,
                created_at=datetime.now(UTC),
            )
            with contextlib.suppress(Exception):
                await self._audit_log_repository.add(entry)

            return resultado

        return wrapper

    return decorator
