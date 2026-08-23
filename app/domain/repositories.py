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
from app.models.usage_log import UsageLog
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
    """`add` existe para onboarding (T1.3, T3.8) — as tools nunca criam usuário."""

    async def add(self, user: User) -> User: ...

    async def get(self, user_id: uuid.UUID) -> User | None: ...

    async def update(self, user_id: uuid.UUID, **changes: object) -> User | None: ...


class ToolAuditLogRepository(Protocol):
    """RF-88. Sem `update`/`delete`: um registro de auditoria nunca é alterado depois de escrito."""

    async def add(self, entry: ToolAuditLog) -> ToolAuditLog: ...

    async def list_by_user(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[ToolAuditLog]: ...


class ConversationRepository(Protocol):
    """Histórico de conversa (RF-65, decisão da Q-07).

    Cada mensagem já chega serializada pelo adapter como um dict JSON-seguro — nunca um
    `ModelMessage` do Pydantic AI (RF-86): o framework de agente não existe deste lado.
    """

    async def append_messages(
        self, user_id: uuid.UUID, messages: list[dict[str, object]]
    ) -> None: ...

    async def list_messages(self, user_id: uuid.UUID) -> list[dict[str, object]]: ...


class UserChannelRepository(Protocol):
    """Resolução de identidade — `chat_id` do canal -> `user_id` interno (RF-02, T3.8).

    `resolve_or_create` é atômica: cria o usuário, as categorias padrão e o vínculo numa
    única operação, ou devolve o `user_id` já vinculado se outra chamada concorrente venceu
    a corrida pelo mesmo `(channel, external_id)` — nunca as duas coisas ao mesmo tempo.
    """

    async def get_user_id(self, channel: str, external_id: str) -> uuid.UUID | None: ...

    async def resolve_or_create(
        self, channel: str, external_id: str, user: User, categories: list[Category]
    ) -> uuid.UUID: ...


class UsageLogRepository(Protocol):
    """Consumo de LLM por interação (RNF-17, RNF-18, T3.10). Sem `update`/`delete`, do mesmo
    jeito que `ToolAuditLogRepository`: um registro de consumo não é alterado depois de escrito."""

    async def add(self, entry: UsageLog) -> UsageLog: ...

    async def list_by_user(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[UsageLog]: ...
