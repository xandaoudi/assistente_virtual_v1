"""Contexto de execução de uma tool (RNF-04, CA-13).

`ToolContext` carrega tudo que uma tool precisa saber sobre quem está chamando e quando.
Toda função do registry tem a assinatura `(ctx: ToolContext, params: XSchema)`: o `ctx`
nunca é serializado para o modelo, e os schemas de parâmetros não têm — e não podem ter —
um campo `user_id`. A identidade do usuário chega só por aqui, injetada do lado do servidor.
"""

import uuid
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ToolContext:
    """Imutável: duas execuções nunca compartilham estado através do mesmo contexto."""

    user_id: uuid.UUID
    timezone: str
    currency: str
    today: date
    idempotency_key: str | None = None
