"""T3.5 — persistência do histórico de conversa (RF-65) e isolamento entre usuários (RNF-04)."""

import uuid

import pytest

from app.core.db import get_session_maker
from app.domain.user_service import UserService
from app.models.user import User
from app.repositories.sqlalchemy import SqlAlchemyConversationRepository

pytestmark = pytest.mark.integration


async def _criar_usuario(nome: str) -> uuid.UUID:
    async with get_session_maker()() as session:
        user = UserService().create_user(nome)
        session.add(user)
        await session.commit()
        return user.id


async def _remover_usuario(user_id: uuid.UUID) -> None:
    async with get_session_maker()() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)  # ON DELETE CASCADE remove conversa e mensagens junto
            await session.commit()


@pytest.mark.asyncio
async def test_historico_persiste_entre_execucoes_e_e_recuperado_por_usuario() -> None:
    user_id = await _criar_usuario("Usuária A")
    repo = SqlAlchemyConversationRepository()
    try:
        assert await repo.list_messages(user_id) == []

        await repo.append_messages(user_id, [{"kind": "request", "text": "oi"}])
        await repo.append_messages(user_id, [{"kind": "response", "text": "olá"}])

        # Uma nova instância do repositório: prova que veio do banco, não de estado em
        # memória do próprio objeto.
        historico = await SqlAlchemyConversationRepository().list_messages(user_id)

        assert historico == [
            {"kind": "request", "text": "oi"},
            {"kind": "response", "text": "olá"},
        ]
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_ordem_das_mensagens_e_preservada_mesmo_gravando_em_lote() -> None:
    user_id = await _criar_usuario("Usuária A")
    repo = SqlAlchemyConversationRepository()
    try:
        # Várias mensagens de um turno só, na mesma chamada — mesmo cenário em que o
        # timestamp do servidor seria idêntico para todas.
        await repo.append_messages(
            user_id, [{"seq": 0}, {"seq": 1}, {"seq": 2}, {"seq": 3}, {"seq": 4}]
        )

        historico = await repo.list_messages(user_id)

        assert historico == [{"seq": i} for i in range(5)]
    finally:
        await _remover_usuario(user_id)


@pytest.mark.asyncio
async def test_historico_de_um_usuario_nunca_aparece_no_de_outro() -> None:
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    repo = SqlAlchemyConversationRepository()
    try:
        await repo.append_messages(user_a, [{"text": "segredo da usuária A"}])
        await repo.append_messages(user_b, [{"text": "segredo do usuário B"}])

        historico_a = await repo.list_messages(user_a)
        historico_b = await repo.list_messages(user_b)

        assert historico_a == [{"text": "segredo da usuária A"}]
        assert historico_b == [{"text": "segredo do usuário B"}]
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)
