import pytest
from sqlalchemy import text

from app.core.db import get_session_maker


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_abre_executa_select_1_e_fecha() -> None:
    async with get_session_maker()() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
