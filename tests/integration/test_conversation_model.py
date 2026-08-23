import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.core.db import get_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


async def _tabelas_existentes_async() -> set[str]:
    async with get_engine().connect() as conn:
        return set(await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))


def _tabelas_existentes() -> set[str]:
    return asyncio.run(_tabelas_existentes_async())


@pytest.mark.integration
def test_upgrade_cria_tabelas_conversations_e_messages_e_downgrade_remove() -> None:
    # Sem @pytest.mark.asyncio de propósito: `command.upgrade`/`downgrade` chamam
    # `asyncio.run()` internamente e não podem rodar dentro de um event loop já ativo.
    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
        assert {"conversations", "messages"} <= _tabelas_existentes()

        # Revisão explícita (não "-1" a partir de head): migrations futuras empilhadas
        # sobre esta não podem quebrar um teste que só quer provar o downgrade *desta*.
        command.downgrade(cfg, "943151c8f5a0")
        assert "messages" not in _tabelas_existentes()
        assert "conversations" not in _tabelas_existentes()
    finally:
        command.upgrade(cfg, "head")
