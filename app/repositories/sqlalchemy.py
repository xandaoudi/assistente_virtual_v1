"""Implementação Postgres dos repositórios do T1.6 — cada método abre e fecha sua sessão.

`user_id` nunca vem só do objeto passado pelo chamador: cada método sobrescreve o campo (em
`add`) ou o usa como cláusula `WHERE` (em todo o resto), para que o filtro seja garantido
pelo repositório, não pela disciplina de quem chama.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import get_session_maker
from app.models.category import Category
from app.models.tool_audit_log import ToolAuditLog
from app.models.transaction import Transaction
from app.models.user import User


class SqlAlchemyTransactionRepository:
    async def add(self, user_id: uuid.UUID, transaction: Transaction) -> Transaction:
        """RF-89: colisão de `idempotency_key` (mesmo em concorrência real, via `UNIQUE` no
        banco) devolve a transação já existente em vez de propagar o erro de integridade."""
        transaction.user_id = user_id
        async with get_session_maker()() as session:
            session.add(transaction)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if transaction.idempotency_key is None:
                    raise
                existente = (
                    await session.execute(
                        select(Transaction).where(
                            Transaction.user_id == user_id,
                            Transaction.idempotency_key == transaction.idempotency_key,
                        )
                    )
                ).scalar_one_or_none()
                if existente is None:
                    raise
                return existente
            return transaction

    async def get(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction | None:
        async with get_session_maker()() as session:
            return (
                await session.execute(
                    select(Transaction).where(
                        Transaction.id == transaction_id,
                        Transaction.user_id == user_id,
                        Transaction.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[Transaction]:
        async with get_session_maker()() as session:
            resultado = await session.execute(
                select(Transaction).where(
                    Transaction.user_id == user_id, Transaction.deleted_at.is_(None)
                )
            )
            return list(resultado.scalars().all())

    async def update(
        self, user_id: uuid.UUID, transaction_id: uuid.UUID, **changes: object
    ) -> Transaction | None:
        async with get_session_maker()() as session:
            transacao = (
                await session.execute(
                    select(Transaction).where(
                        Transaction.id == transaction_id,
                        Transaction.user_id == user_id,
                        Transaction.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if transacao is None:
                return None
            for campo, valor in changes.items():
                setattr(transacao, campo, valor)
            await session.commit()
            return transacao

    async def delete(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> bool:
        async with get_session_maker()() as session:
            transacao = (
                await session.execute(
                    select(Transaction).where(
                        Transaction.id == transaction_id,
                        Transaction.user_id == user_id,
                        Transaction.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if transacao is None:
                return False
            transacao.deleted_at = datetime.now(UTC)
            await session.commit()
            return True


class SqlAlchemyCategoryRepository:
    async def add(self, user_id: uuid.UUID, category: Category) -> Category:
        category.user_id = user_id
        async with get_session_maker()() as session:
            session.add(category)
            await session.commit()
            return category

    async def get(self, user_id: uuid.UUID, category_id: uuid.UUID) -> Category | None:
        async with get_session_maker()() as session:
            return (
                await session.execute(
                    select(Category).where(Category.id == category_id, Category.user_id == user_id)
                )
            ).scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[Category]:
        async with get_session_maker()() as session:
            resultado = await session.execute(select(Category).where(Category.user_id == user_id))
            return list(resultado.scalars().all())

    async def update(
        self, user_id: uuid.UUID, category_id: uuid.UUID, **changes: object
    ) -> Category | None:
        async with get_session_maker()() as session:
            categoria = (
                await session.execute(
                    select(Category).where(Category.id == category_id, Category.user_id == user_id)
                )
            ).scalar_one_or_none()
            if categoria is None:
                return None
            for campo, valor in changes.items():
                setattr(categoria, campo, valor)
            await session.commit()
            return categoria


class SqlAlchemyUserRepository:
    async def get(self, user_id: uuid.UUID) -> User | None:
        async with get_session_maker()() as session:
            return (
                await session.execute(
                    select(User).where(User.id == user_id, User.deleted_at.is_(None))
                )
            ).scalar_one_or_none()

    async def update(self, user_id: uuid.UUID, **changes: object) -> User | None:
        async with get_session_maker()() as session:
            user = (
                await session.execute(
                    select(User).where(User.id == user_id, User.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            if user is None:
                return None
            for campo, valor in changes.items():
                setattr(user, campo, valor)
            await session.commit()
            return user


class SqlAlchemyToolAuditLogRepository:
    async def add(self, entry: ToolAuditLog) -> ToolAuditLog:
        async with get_session_maker()() as session:
            session.add(entry)
            await session.commit()
            return entry

    async def list_by_user(
        self, user_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[ToolAuditLog]:
        async with get_session_maker()() as session:
            resultado = await session.execute(
                select(ToolAuditLog).where(
                    ToolAuditLog.user_id == user_id,
                    ToolAuditLog.created_at >= start,
                    ToolAuditLog.created_at <= end,
                )
            )
            return list(resultado.scalars().all())
