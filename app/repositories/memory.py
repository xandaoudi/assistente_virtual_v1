"""Repositórios em memória — mesma semântica de filtro por `user_id` da implementação real.

Existem para o RNF-33 (teste unitário sem banco): `app.repositories.sqlalchemy` é a única
implementação usada em produção. O chamador deve gerar `.id` antes de `add` (não há flush
para preencher um default aqui, como faz o banco).
"""

import uuid
from datetime import UTC, datetime

from app.models.category import Category
from app.models.tool_audit_log import ToolAuditLog
from app.models.transaction import Transaction
from app.models.usage_log import UsageLog
from app.models.user import User


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, list[dict[str, object]]] = {}

    async def append_messages(self, user_id: uuid.UUID, messages: list[dict[str, object]]) -> None:
        self._store.setdefault(user_id, []).extend(messages)

    async def list_messages(self, user_id: uuid.UUID) -> list[dict[str, object]]:
        return list(self._store.get(user_id, []))


class InMemoryTransactionRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Transaction] = {}

    async def add(self, user_id: uuid.UUID, transaction: Transaction) -> Transaction:
        transaction.user_id = user_id
        if transaction.idempotency_key is not None:
            existente = self._por_idempotency_key(user_id, transaction.idempotency_key)
            if existente is not None:
                return existente
        self._store[transaction.id] = transaction
        return transaction

    def _por_idempotency_key(self, user_id: uuid.UUID, idempotency_key: str) -> Transaction | None:
        for transacao in self._store.values():
            if transacao.user_id == user_id and transacao.idempotency_key == idempotency_key:
                return transacao
        return None

    async def get(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction | None:
        transacao = self._store.get(transaction_id)
        if transacao is None or transacao.user_id != user_id or transacao.deleted_at is not None:
            return None
        return transacao

    async def list_by_user(self, user_id: uuid.UUID) -> list[Transaction]:
        return [
            transacao
            for transacao in self._store.values()
            if transacao.user_id == user_id and transacao.deleted_at is None
        ]

    async def update(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, **changes: object
    ) -> Transaction | None:
        transacao = self._store.get(transaction_id)
        if transacao is None or transacao.user_id != user_id or transacao.deleted_at is not None:
            return None
        for campo, valor in changes.items():
            setattr(transacao, campo, valor)
        return transacao

    async def delete(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> bool:
        transacao = self._store.get(transaction_id)
        if transacao is None or transacao.user_id != user_id or transacao.deleted_at is not None:
            return False
        transacao.deleted_at = datetime.now(UTC)
        return True


class InMemoryCategoryRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, Category] = {}

    async def add(self, user_id: uuid.UUID, category: Category) -> Category:
        category.user_id = user_id
        self._store[category.id] = category
        return category

    async def get(self, user_id: uuid.UUID, category_id: uuid.UUID) -> Category | None:
        categoria = self._store.get(category_id)
        if categoria is None or categoria.user_id != user_id:
            return None
        return categoria

    async def list_by_user(self, user_id: uuid.UUID) -> list[Category]:
        return [categoria for categoria in self._store.values() if categoria.user_id == user_id]

    async def update(
        self, user_id: uuid.UUID, category_id: uuid.UUID, **changes: object
    ) -> Category | None:
        categoria = self._store.get(category_id)
        if categoria is None or categoria.user_id != user_id:
            return None
        for campo, valor in changes.items():
            setattr(categoria, campo, valor)
        return categoria


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._store: dict[uuid.UUID, User] = {}

    async def add(self, user: User) -> User:
        self._store[user.id] = user
        return user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return self._store.get(user_id)

    async def update(self, user_id: uuid.UUID, **changes: object) -> User | None:
        user = self._store.get(user_id)
        if user is None:
            return None
        for campo, valor in changes.items():
            setattr(user, campo, valor)
        return user


class InMemoryToolAuditLogRepository:
    def __init__(self) -> None:
        self._store: list[ToolAuditLog] = []

    async def add(self, entry: ToolAuditLog) -> ToolAuditLog:
        self._store.append(entry)
        return entry

    async def list_by_user(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[ToolAuditLog]:
        return [
            entry
            for entry in self._store
            if entry.user_id == user_id and start <= entry.created_at <= end
        ]


class InMemoryUserChannelRepository:
    """Sem concorrência real de propósito — a corrida pelo mesmo `(channel, external_id)`
    só é possível contra um banco de verdade (ver `SqlAlchemyUserChannelRepository`)."""

    def __init__(self) -> None:
        self._links: dict[tuple[str, str], uuid.UUID] = {}
        self.users: dict[uuid.UUID, User] = {}
        self.categories: dict[uuid.UUID, list[Category]] = {}

    async def get_user_id(self, channel: str, external_id: str) -> uuid.UUID | None:
        return self._links.get((channel, external_id))

    async def resolve_or_create(
        self, channel: str, external_id: str, user: User, categories: list[Category]
    ) -> uuid.UUID:
        existente = self._links.get((channel, external_id))
        if existente is not None:
            return existente
        self._links[(channel, external_id)] = user.id
        self.users[user.id] = user
        self.categories[user.id] = categories
        return user.id


class InMemoryUsageLogRepository:
    def __init__(self) -> None:
        self._store: list[UsageLog] = []

    async def add(self, entry: UsageLog) -> UsageLog:
        self._store.append(entry)
        return entry

    async def list_by_user(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[UsageLog]:
        return [
            entry
            for entry in self._store
            if entry.user_id == user_id and start <= entry.created_at <= end
        ]
