import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.tool_audit_log import ToolAuditLog

from app.domain.enums import TransactionSource, TransactionType
from app.domain.repositories import (
    CategoryRepository,
    ToolAuditLogRepository,
    TransactionRepository,
    UserRepository,
)
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories.memory import (
    InMemoryCategoryRepository,
    InMemoryToolAuditLogRepository,
    InMemoryTransactionRepository,
    InMemoryUserRepository,
)

pytestmark = pytest.mark.unit


def _novo_usuario() -> User:
    return User(
        id=uuid.uuid4(),
        name="Alexandre",
        timezone="America/Sao_Paulo",
        currency="BRL",
        locale="pt_BR",
    )


def _nova_transacao(user_id: uuid.UUID) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        type=TransactionType.EXPENSE,
        amount=Decimal("50.00"),
        currency="BRL",
        date=date(2026, 8, 21),
        source=TransactionSource.CHAT,
    )


def _nova_categoria(user_id: uuid.UUID, name: str = "Mercado") -> Category:
    return Category(id=uuid.uuid4(), user_id=user_id, name=name, type=TransactionType.EXPENSE)


@pytest.mark.asyncio
async def test_repositorio_em_memoria_de_transacoes_respeita_filtro_por_usuario() -> None:
    # Anotado com o Protocol para o mypy confirmar que a implementação satisfaz o contrato.
    repo: TransactionRepository = InMemoryTransactionRepository()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    transacao = await repo.add(user_a, _nova_transacao(user_a))

    assert await repo.get(user_b, transacao.id) is None
    assert await repo.get(user_a, transacao.id) is transacao

    assert await repo.list_by_user(user_b) == []
    assert await repo.list_by_user(user_a) == [transacao]

    assert await repo.update(user_b, transacao.id, amount=Decimal("999.00")) is None
    assert transacao.amount == Decimal("50.00")

    assert await repo.delete(user_b, transacao.id) is False
    assert await repo.get(user_a, transacao.id) is transacao

    atualizada = await repo.update(user_a, transacao.id, description="Padaria")
    assert atualizada is not None
    assert atualizada.description == "Padaria"

    assert await repo.delete(user_a, transacao.id) is True
    assert await repo.get(user_a, transacao.id) is None


@pytest.mark.asyncio
async def test_update_apos_soft_delete_nao_ressuscita_a_transacao() -> None:
    repo: TransactionRepository = InMemoryTransactionRepository()
    user_id = uuid.uuid4()
    transacao = await repo.add(user_id, _nova_transacao(user_id))

    assert await repo.delete(user_id, transacao.id) is True

    resultado = await repo.update(user_id, transacao.id, amount=Decimal("1.00"))

    assert resultado is None


@pytest.mark.asyncio
async def test_repositorio_em_memoria_de_categorias_respeita_filtro_por_usuario() -> None:
    repo: CategoryRepository = InMemoryCategoryRepository()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    categoria = await repo.add(user_a, _nova_categoria(user_a))

    assert await repo.get(user_b, categoria.id) is None
    assert await repo.get(user_a, categoria.id) is categoria

    assert await repo.list_by_user(user_b) == []
    assert await repo.list_by_user(user_a) == [categoria]

    assert await repo.update(user_b, categoria.id, name="Roubada") is None
    assert categoria.name == "Mercado"

    renomeada = await repo.update(user_a, categoria.id, name="Super")
    assert renomeada is not None
    assert renomeada.name == "Super"


@pytest.mark.asyncio
async def test_repositorio_em_memoria_de_usuarios_get_e_update() -> None:
    repo: UserRepository = InMemoryUserRepository()
    usuario = _novo_usuario()
    await repo.add(usuario)

    assert await repo.get(uuid.uuid4()) is None
    assert await repo.get(usuario.id) is usuario

    assert await repo.update(uuid.uuid4(), timezone="Europe/Lisbon") is None

    atualizado = await repo.update(usuario.id, timezone="Europe/Lisbon", currency="EUR")
    assert atualizado is not None
    assert atualizado.timezone == "Europe/Lisbon"
    assert atualizado.currency == "EUR"


@pytest.mark.asyncio
async def test_repositorio_em_memoria_de_auditoria_add_e_list_by_user() -> None:
    repo: ToolAuditLogRepository = InMemoryToolAuditLogRepository()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    agora = datetime.now(UTC)

    entrada = ToolAuditLog(
        id=uuid.uuid4(),
        user_id=user_a,
        tool_name="create_transaction",
        params={"type": "expense"},
        result_status="success",
        duration_ms=5,
        created_at=agora,
    )
    await repo.add(entrada)

    assert (
        await repo.list_by_user(user_b, agora - timedelta(days=1), agora + timedelta(days=1)) == []
    )

    encontrados = await repo.list_by_user(
        user_a, agora - timedelta(days=1), agora + timedelta(days=1)
    )
    assert encontrados == [entrada]

    fora_do_periodo = await repo.list_by_user(
        user_a, agora + timedelta(days=1), agora + timedelta(days=2)
    )
    assert fora_do_periodo == []
