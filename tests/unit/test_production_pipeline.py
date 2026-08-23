"""T3.14 — monta o `ResolveDeps` de produção: `chat_id` (T3.8) -> `user_id` -> `Deps` completo
do agente, com fuso e moeda do usuário de verdade (não um default fixo — RF-46/RF-48 deixam o
usuário mudar preferências, e a próxima mensagem precisa refletir isso)."""

import pytest

from app.adapters.channel_message import ChannelMessage
from app.adapters.production import build_resolve_deps
from app.domain.identity_service import IdentityService
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserChannelRepository,
    InMemoryUserRepository,
)
from app.tools.registry import ToolRegistry

pytestmark = pytest.mark.unit


def _nova_registry() -> ToolRegistry:
    return ToolRegistry(
        InMemoryTransactionRepository(),
        InMemoryCategoryRepository(),
        InMemoryUserRepository(),
        InMemoryToolAuditLogRepository(),
    )


def _mensagem(external_user_id: str = "555") -> ChannelMessage:
    import datetime as dt

    return ChannelMessage(
        channel="telegram",
        external_user_id=external_user_id,
        text="oi",
        media=None,
        timestamp=dt.datetime.fromtimestamp(1735000000, tz=dt.UTC),
        message_id="700",
    )


@pytest.mark.asyncio
async def test_resolve_deps_usa_fuso_e_moeda_reais_do_usuario_ja_resolvido() -> None:
    channels_repo = InMemoryUserChannelRepository()
    identity_service = IdentityService(channels_repo)
    users_repo = InMemoryUserRepository()

    # Cria o usuário via IdentityService (T3.8) e replica na `UserRepository` separada —
    # no Postgres real as duas apontam pra mesma tabela; só no dublê em memória elas são
    # instâncias distintas, então o teste sincroniza manualmente o que o commit real garante.
    user_id = await identity_service.resolve_user_id("telegram", "555")
    await users_repo.add(channels_repo.users[user_id])
    await users_repo.update(user_id, timezone="Europe/Lisbon", currency="EUR")

    resolve_deps = build_resolve_deps(
        identity_service=identity_service, users=users_repo, tools_factory=_nova_registry
    )

    deps = await resolve_deps(_mensagem())

    assert deps.user_id == user_id
    assert deps.timezone == "Europe/Lisbon"
    assert deps.currency == "EUR"
    assert deps.idempotency_key == "telegram:700"


@pytest.mark.asyncio
async def test_resolve_deps_resolve_o_mesmo_usuario_para_o_mesmo_chat_id() -> None:
    channels_repo = InMemoryUserChannelRepository()
    identity_service = IdentityService(channels_repo)
    users_repo = InMemoryUserRepository()
    user_id = await identity_service.resolve_user_id("telegram", "555")
    await users_repo.add(channels_repo.users[user_id])

    resolve_deps = build_resolve_deps(
        identity_service=identity_service, users=users_repo, tools_factory=_nova_registry
    )

    deps_1 = await resolve_deps(_mensagem("555"))
    deps_2 = await resolve_deps(_mensagem("555"))

    assert deps_1.user_id == deps_2.user_id == user_id


@pytest.mark.asyncio
async def test_resolve_deps_da_um_registry_novo_a_cada_chamada() -> None:
    channels_repo = InMemoryUserChannelRepository()
    identity_service = IdentityService(channels_repo)
    users_repo = InMemoryUserRepository()
    user_id = await identity_service.resolve_user_id("telegram", "555")
    await users_repo.add(channels_repo.users[user_id])

    resolve_deps = build_resolve_deps(
        identity_service=identity_service, users=users_repo, tools_factory=_nova_registry
    )

    deps_1 = await resolve_deps(_mensagem())
    deps_2 = await resolve_deps(_mensagem())

    assert deps_1.tools is not deps_2.tools
