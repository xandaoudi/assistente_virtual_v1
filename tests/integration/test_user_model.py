import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.core.db import get_engine, get_session_maker
from app.domain.user_service import UserService
from app.models.user import User

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


async def _tabelas_existentes_async() -> set[str]:
    async with get_engine().connect() as conn:
        return set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))


def _tabelas_existentes() -> set[str]:
    return asyncio.run(_tabelas_existentes_async())


@pytest.mark.integration
def test_upgrade_cria_tabela_users_e_downgrade_remove() -> None:
    # Sem @pytest.mark.asyncio de propósito: `command.upgrade`/`downgrade` chamam
    # `asyncio.run()` internamente (ver alembic/env.py) e não podem rodar dentro de
    # um event loop já ativo.
    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
        assert "users" in _tabelas_existentes()

        command.downgrade(cfg, "base")
        assert "users" not in _tabelas_existentes()
    finally:
        command.upgrade(cfg, "head")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_usuario_persiste_e_e_recuperado_com_mesmos_valores() -> None:
    user = UserService().create_user("Alexandre")

    async with get_session_maker()() as session:
        session.add(user)
        await session.commit()

        try:
            recuperado = await session.get(User, user.id)
            assert recuperado is not None
            assert recuperado.name == "Alexandre"
            assert recuperado.timezone == "America/Sao_Paulo"
            assert recuperado.currency == "BRL"
            assert recuperado.locale == "pt_BR"
        finally:
            await session.delete(user)
            await session.commit()
