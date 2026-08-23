"""T3.8 — resolução de identidade contra o Postgres de verdade: unicidade e concorrência
sobre `(channel, external_id)`, garantidas pelo `UNIQUE` da tabela `user_channels`."""

import asyncio
import uuid

import pytest

from app.core.db import get_session_maker
from app.domain.identity_service import IdentityService
from app.models.user import User
from app.repositories.sqlalchemy import SqlAlchemyUserChannelRepository

pytestmark = pytest.mark.integration


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)  # ON DELETE CASCADE remove categorias e vínculo junto
            await session.commit()


def _novo_servico() -> IdentityService:
    return IdentityService(SqlAlchemyUserChannelRepository())


@pytest.mark.asyncio
async def test_duas_mensagens_do_mesmo_chat_id_resolvem_para_o_mesmo_usuario() -> None:
    servico = _novo_servico()
    external_id = f"chat-{uuid.uuid4()}"

    primeiro = await servico.resolve_user_id("telegram", external_id)
    try:
        segundo = await servico.resolve_user_id("telegram", external_id)
        assert primeiro == segundo
    finally:
        await _remover_usuario(primeiro)


@pytest.mark.asyncio
async def test_chat_ids_diferentes_nunca_colidem() -> None:
    servico = _novo_servico()
    external_a = f"chat-{uuid.uuid4()}"
    external_b = f"chat-{uuid.uuid4()}"

    user_a = await servico.resolve_user_id("telegram", external_a)
    try:
        user_b = await servico.resolve_user_id("telegram", external_b)
        try:
            assert user_a != user_b
        finally:
            await _remover_usuario(user_b)
    finally:
        await _remover_usuario(user_a)


@pytest.mark.asyncio
async def test_criacao_concorrente_do_mesmo_chat_id_gera_um_usuario() -> None:
    external_id = f"chat-{uuid.uuid4()}"

    resultados = await asyncio.gather(
        *(_novo_servico().resolve_user_id("telegram", external_id) for _ in range(10))
    )
    try:
        assert len(set(resultados)) == 1
    finally:
        await _remover_usuario(resultados[0])
