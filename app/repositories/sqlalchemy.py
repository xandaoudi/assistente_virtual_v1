"""Implementação Postgres dos repositórios do T1.6 — cada método abre e fecha sua sessão.

`user_id` nunca vem só do objeto passado pelo chamador: cada método sobrescreve o campo (em
`add`) ou o usa como cláusula `WHERE` (em todo o resto), para que o filtro seja garantido
pelo repositório, não pela disciplina de quem chama.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import get_session_maker
from app.models.category import Category
from app.models.transaction import Transaction


class SqlAlchemyTransactionRepository:
    async def add(self, user_id: uuid.UUID, transaction: Transaction) -> Transaction:
        transaction.user_id = user_id
        async with get_session_maker()() as session:
            session.add(transaction)
            await session.commit()
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
