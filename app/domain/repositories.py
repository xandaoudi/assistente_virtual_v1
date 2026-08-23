"""Contratos de repositório (RNF-04): `user_id` é parâmetro obrigatório de todo método.

Duas implementações satisfazem este contrato: `app.repositories.sqlalchemy` (produção,
Postgres) e `app.repositories.memory` (testes unitários, sem banco — RNF-33). Nenhum método
aceita `user_id` opcional nem tem variante "sem filtro" — se pudesse, um dia seria chamado
sem ele.
"""

import uuid
from datetime import datetime
from typing import Protocol

from app.models.category import Category
from app.models.tool_audit_log import ToolAuditLog
from app.models.transaction import Transaction
from app.models.user import User


class TransactionRepository(Protocol):
    async def add(self, user_id: uuid.UUID, transaction: Transaction) -> Transaction: ...

    async def get(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction | None: ...

    async def list_by_user(self, user_id: uuid.UUID) -> list[Transaction]: ...

    async def update(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, **changes: object
    ) -> Transaction | None: ...

    async def delete(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> bool: ...


class CategoryRepository(Protocol):
    async def add(self, user_id: uuid.UUID, category: Category) -> Category: ...

    async def get(self, user_id: uuid.UUID, category_id: uuid.UUID) -> Category | None: ...

    async def list_by_user(self, user_id: uuid.UUID) -> list[Category]: ...

    async def update(
        self, user_id: uuid.UUID, category_id: uuid.UUID, **changes: object
    ) -> Category | None: ...


class UserRepository(Protocol):
    """Sem `add`: criar usuário é onboarding (T1.3/Etapa 4), não escopo das tools."""

    async def get(self, user_id: uuid.UUID) -> User | None: ...

    async def update(self, user_id: uuid.UUID, **changes: object) -> User | None: ...


class ToolAuditLogRepository(Protocol):
    """RF-88. Sem `update`/`delete`: um registro de auditoria nunca é alterado depois de escrito."""

    async def add(self, entry: ToolAuditLog) -> ToolAuditLog: ...

    async def list_by_user(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[ToolAuditLog]: ...
