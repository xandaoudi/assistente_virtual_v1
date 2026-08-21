"""Gerenciamento de categorias do usuário (RF-46, RF-47, RF-48)."""

import uuid

from app.domain.enums import TransactionType
from app.domain.repositories import CategoryRepository
from app.models.category import Category


class CategoryService:
    def __init__(self, repository: CategoryRepository) -> None:
        self._repository = repository

    async def list_categories(
        self, user_id: uuid.UUID, *, category_type: TransactionType | None = None
    ) -> list[Category]:
        """Lista as categorias ativas do usuário — as desativadas (RF-47) ficam de fora."""
        categorias = await self._repository.list_by_user(user_id)
        return [
            categoria
            for categoria in categorias
            if categoria.is_active and (category_type is None or categoria.type == category_type)
        ]

    async def create_category(
        self, user_id: uuid.UUID, name: str, category_type: TransactionType
    ) -> Category:
        # `is_active`/`is_default` são explícitos aqui, não deixados para o default da
        # coluna: esse default só é aplicado no flush de uma sessão real (ver T1.3), e o
        # repositório em memória (RNF-33) nunca passa por um.
        categoria = Category(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            type=category_type,
            is_default=False,
            is_active=True,
        )
        return await self._repository.add(user_id, categoria)

    async def rename_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID, new_name: str
    ) -> Category | None:
        return await self._repository.update(user_id, category_id, name=new_name)

    async def deactivate_category(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> Category | None:
        """Desativa a categoria (RF-47) — nunca apaga nem desvincula transações históricas."""
        return await self._repository.update(user_id, category_id, is_active=False)
