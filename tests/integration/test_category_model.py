import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import get_session_maker
from app.domain.default_categories import build_default_categories
from app.domain.enums import TransactionType
from app.domain.user_service import UserService
from app.models.category import Category
from app.models.user import User

pytestmark = pytest.mark.integration


async def _criar_usuario_com_categorias_padrao(nome: str) -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user(nome)
        session.add(user)
        await session.flush()  # sem relationship() ORM, o insert de user precisa vir antes
        session.add_all(build_default_categories(user.id))
        await session.commit()
        return user.id


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)  # ON DELETE CASCADE remove as categorias junto
            await session.commit()


@pytest.mark.asyncio
async def test_criar_usuario_gera_as_dez_categorias_vinculadas_a_ele() -> None:
    user_id = await _criar_usuario_com_categorias_padrao("Alexandre")
    try:
        async with get_session_maker()() as session:
            categorias = (
                (await session.execute(select(Category).where(Category.user_id == user_id)))
                .scalars()
                .all()
            )
        assert len(categorias) == 10
        assert all(categoria.is_default for categoria in categorias)
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_dois_usuarios_tem_conjuntos_independentes() -> None:
    user_a_id = await _criar_usuario_com_categorias_padrao("Usuária A")
    user_b_id = await _criar_usuario_com_categorias_padrao("Usuário B")
    try:
        async with get_session_maker()() as session:
            mercado_a = (
                await session.execute(
                    select(Category).where(
                        Category.user_id == user_a_id, Category.name == "Mercado"
                    )
                )
            ).scalar_one()
            mercado_a.name = "Super"
            await session.commit()

        async with get_session_maker()() as session:
            mercado_a_renomeada = (
                await session.execute(
                    select(Category).where(Category.user_id == user_a_id, Category.name == "Super")
                )
            ).scalar_one_or_none()
            mercado_b_intacta = (
                await session.execute(
                    select(Category).where(
                        Category.user_id == user_b_id, Category.name == "Mercado"
                    )
                )
            ).scalar_one_or_none()

        assert mercado_a_renomeada is not None
        assert mercado_b_intacta is not None
    finally:
        await _remover_usuario(user_a_id)
        await _remover_usuario(user_b_id)


@pytest.mark.asyncio
async def test_nome_duplicado_mesmo_usuario_e_tipo_e_rejeitado_pelo_banco() -> None:
    async with get_session_maker()() as session:
        user = UserService().create_user("Duplicidade")
        session.add(user)
        await session.flush()
        session.add(Category(user_id=user.id, name="Presentes", type=TransactionType.EXPENSE))
        await session.commit()
        user_id = user.id

    try:
        async with get_session_maker()() as session:
            session.add(Category(user_id=user_id, name="Presentes", type=TransactionType.EXPENSE))
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_nome_igual_em_usuarios_diferentes_e_permitido() -> None:
    user_a = UserService().create_user("A")
    user_b = UserService().create_user("B")
    try:
        async with get_session_maker()() as session:
            session.add_all([user_a, user_b])
            await session.flush()
            session.add_all(
                [
                    Category(user_id=user_a.id, name="Presentes", type=TransactionType.EXPENSE),
                    Category(user_id=user_b.id, name="Presentes", type=TransactionType.EXPENSE),
                ]
            )
            await session.commit()  # não deve levantar IntegrityError
    finally:
        await _remover_usuario(user_a.id)
        await _remover_usuario(user_b.id)
