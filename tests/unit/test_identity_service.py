"""T3.8 — resolução de identidade: `chat_id` do canal -> `user_id` interno (RF-02)."""

import pytest

from app.domain.default_categories import DEFAULT_CATEGORY_NAMES
from app.domain.identity_service import IdentityService
from app.domain.user_service import DEFAULT_CURRENCY, DEFAULT_TIMEZONE
from app.repositories.memory import InMemoryUserChannelRepository

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_chat_id_conhecido_resolve_para_o_usuario_correto() -> None:
    repo = InMemoryUserChannelRepository()
    service = IdentityService(repo)

    primeiro = await service.resolve_user_id("telegram", "555")
    segundo = await service.resolve_user_id("telegram", "555")

    assert primeiro == segundo
    assert len(repo.users) == 1


@pytest.mark.asyncio
async def test_chat_id_novo_cria_usuario_com_os_padroes() -> None:
    repo = InMemoryUserChannelRepository()
    service = IdentityService(repo)

    user_id = await service.resolve_user_id("telegram", "777")

    usuario = repo.users[user_id]
    assert usuario.timezone == DEFAULT_TIMEZONE == "America/Sao_Paulo"
    assert usuario.currency == DEFAULT_CURRENCY == "BRL"

    categorias = repo.categories[user_id]
    assert {categoria.name for categoria in categorias} == set(DEFAULT_CATEGORY_NAMES)
    assert all(categoria.user_id == user_id for categoria in categorias)


@pytest.mark.asyncio
async def test_chat_ids_diferentes_nunca_colidem() -> None:
    repo = InMemoryUserChannelRepository()
    service = IdentityService(repo)

    user_a = await service.resolve_user_id("telegram", "111")
    user_b = await service.resolve_user_id("telegram", "222")

    assert user_a != user_b
