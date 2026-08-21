"""Categorias padrão criadas automaticamente para todo novo usuário (RF-45)."""

import uuid

from app.domain.enums import TransactionType
from app.models.category import Category

DEFAULT_CATEGORY_NAMES: tuple[str, ...] = (
    "Alimentação",
    "Mercado",
    "Transporte",
    "Moradia",
    "Saúde",
    "Educação",
    "Lazer",
    "Vestuário",
    "Assinaturas",
    "Outros",
)


def build_default_categories(user_id: uuid.UUID) -> list[Category]:
    """Monta as categorias padrão de despesa de um usuário nascente, sem persistir.

    O `CategoryService` completo (listar, criar, renomear, desativar) é o T1.7; esta
    função só existe para acompanhar a criação do usuário com o conjunto inicial do RF-45.
    """
    return [
        Category(
            id=uuid.uuid4(),
            user_id=user_id,
            name=name,
            type=TransactionType.EXPENSE,
            is_default=True,
            is_active=True,
        )
        for name in DEFAULT_CATEGORY_NAMES
    ]
