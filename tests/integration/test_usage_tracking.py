"""T3.10 — consumo acumulado por usuário e período, contra o Postgres de verdade
(RNF-17, RNF-18)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.db import get_session_maker
from app.domain.usage_service import UsageService
from app.domain.user_service import UserService
from app.models.user import User
from app.repositories.sqlalchemy import SqlAlchemyUsageLogRepository

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
            await session.delete(user)  # ON DELETE CASCADE remove os registros de uso junto
            await session.commit()


@pytest.mark.asyncio
async def test_consumo_acumulado_e_consultavel_por_usuario_e_periodo() -> None:
    user_a = await _criar_usuario("Usuária com consumo")
    user_b = await _criar_usuario("Usuário sem consumo no período")
    try:
        service = UsageService(SqlAlchemyUsageLogRepository())
        agora = datetime.now(UTC)

        await service.record(
            user_a, requests=1, input_tokens=100, output_tokens=20, cache_read_tokens=30
        )
        await service.record(
            user_a, requests=2, input_tokens=200, output_tokens=40, cache_read_tokens=50
        )
        # Consumo de outro usuário não pode vazar para o resumo de user_a (RNF-04).
        await service.record(user_b, requests=1, input_tokens=999, output_tokens=999)

        resumo = await service.summarize(
            user_a, agora - timedelta(minutes=1), agora + timedelta(minutes=1)
        )

        assert resumo.requests == 3
        assert resumo.input_tokens == 300
        assert resumo.output_tokens == 60
        assert resumo.cache_read_tokens == 80
        assert resumo.cache_hit_ratio == pytest.approx(80 / 300)

        fora_do_periodo = await service.summarize(
            user_a, agora - timedelta(days=2), agora - timedelta(days=1)
        )
        assert fora_do_periodo.requests == 0
        assert fora_do_periodo.cache_hit_ratio is None
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)
