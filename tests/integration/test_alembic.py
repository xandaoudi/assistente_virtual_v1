from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


@pytest.mark.integration
def test_upgrade_head_on_clean_database() -> None:
    command.upgrade(_alembic_config(), "head")


@pytest.mark.integration
def test_downgrade_base_then_upgrade_head() -> None:
    cfg = _alembic_config()

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
