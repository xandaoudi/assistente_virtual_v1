import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import TransactionSource, TransactionType
from app.domain.finance_service import FinanceService
from app.models.category import Category
from app.models.transaction import Transaction
from app.repositories.memory import InMemoryCategoryRepository, InMemoryTransactionRepository

pytestmark = pytest.mark.unit

_INICIO = date(2026, 7, 1)
_FIM = date(2026, 7, 31)


def _nova_transacao(
    user_id: uuid.UUID,
    *,
    transaction_type: TransactionType,
    amount: Decimal,
    transaction_date: date,
    category_id: uuid.UUID | None = None,
) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        type=transaction_type,
        amount=amount,
        currency="BRL",
        category_id=category_id,
        date=transaction_date,
        source=TransactionSource.CHAT,
    )


def _nova_categoria(user_id: uuid.UUID, name: str) -> Category:
    return Category(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        type=TransactionType.EXPENSE,
        is_active=True,
        is_default=False,
    )


def _novo_service() -> tuple[
    FinanceService, InMemoryTransactionRepository, InMemoryCategoryRepository
]:
    transaction_repo = InMemoryTransactionRepository()
    category_repo = InMemoryCategoryRepository()
    return FinanceService(transaction_repo, category_repo), transaction_repo, category_repo


@pytest.mark.asyncio
async def test_total_de_despesas_do_periodo() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("100.00"),
            transaction_date=date(2026, 7, 10),
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("50.00"),
            transaction_date=date(2026, 7, 15),
        ),
    )

    resumo = await service.get_summary(user_id, _INICIO, _FIM)

    assert resumo.total_expenses == Decimal("150.00")


@pytest.mark.asyncio
async def test_total_de_receitas_do_periodo() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("3000.00"),
            transaction_date=date(2026, 7, 5),
        ),
    )

    resumo = await service.get_summary(user_id, _INICIO, _FIM)

    assert resumo.total_income == Decimal("3000.00")


@pytest.mark.asyncio
async def test_saldo_e_receitas_menos_despesas_inclusive_negativo() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("100.00"),
            transaction_date=date(2026, 7, 5),
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("300.00"),
            transaction_date=date(2026, 7, 10),
        ),
    )

    resumo = await service.get_summary(user_id, _INICIO, _FIM)

    assert resumo.balance == Decimal("-200.00")


@pytest.mark.asyncio
async def test_agrupamento_por_categoria_com_valor_e_percentual() -> None:
    service, transaction_repo, category_repo = _novo_service()
    user_id = uuid.uuid4()
    mercado = await category_repo.add(user_id, _nova_categoria(user_id, "Mercado"))
    lazer = await category_repo.add(user_id, _nova_categoria(user_id, "Lazer"))
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("75.00"),
            transaction_date=date(2026, 7, 10),
            category_id=mercado.id,
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("25.00"),
            transaction_date=date(2026, 7, 12),
            category_id=lazer.id,
        ),
    )

    agrupado = await service.get_spending_by_category(user_id, _INICIO, _FIM)

    por_nome = {item["category"]: item for item in agrupado}
    assert por_nome["Mercado"]["total"] == Decimal("75.00")
    assert por_nome["Mercado"]["percent"] == 75.0
    assert por_nome["Mercado"]["count"] == 1
    assert por_nome["Lazer"]["total"] == Decimal("25.00")
    assert por_nome["Lazer"]["percent"] == 25.0
    assert por_nome["Lazer"]["count"] == 1


@pytest.mark.asyncio
async def test_percentuais_somam_100() -> None:
    service, transaction_repo, category_repo = _novo_service()
    user_id = uuid.uuid4()
    categoria_a = await category_repo.add(user_id, _nova_categoria(user_id, "A"))
    categoria_b = await category_repo.add(user_id, _nova_categoria(user_id, "B"))
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("60.00"),
            transaction_date=date(2026, 7, 1),
            category_id=categoria_a.id,
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("40.00"),
            transaction_date=date(2026, 7, 2),
            category_id=categoria_b.id,
        ),
    )

    agrupado = await service.get_spending_by_category(user_id, _INICIO, _FIM)

    assert sum(item["percent"] for item in agrupado) == 100.0


@pytest.mark.asyncio
async def test_total_de_uma_categoria_especifica() -> None:
    service, transaction_repo, category_repo = _novo_service()
    user_id = uuid.uuid4()
    mercado = await category_repo.add(user_id, _nova_categoria(user_id, "Mercado"))
    lazer = await category_repo.add(user_id, _nova_categoria(user_id, "Lazer"))
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("40.00"),
            transaction_date=date(2026, 7, 5),
            category_id=mercado.id,
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("999.00"),
            transaction_date=date(2026, 7, 6),
            category_id=lazer.id,
        ),
    )

    total = await service.get_category_spending(user_id, _INICIO, _FIM, mercado.id)

    assert total == Decimal("40.00")


@pytest.mark.asyncio
async def test_periodo_sem_transacoes_devolve_zeros() -> None:
    service, _, _ = _novo_service()
    user_id = uuid.uuid4()

    resumo = await service.get_summary(user_id, _INICIO, _FIM)
    agrupado = await service.get_spending_by_category(user_id, _INICIO, _FIM)

    assert resumo.total_expenses == Decimal("0.00")
    assert resumo.total_income == Decimal("0.00")
    assert resumo.balance == Decimal("0.00")
    assert agrupado == []


@pytest.mark.asyncio
async def test_transacoes_na_borda_do_periodo_entram() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("10.00"),
            transaction_date=_INICIO,
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("20.00"),
            transaction_date=_FIM,
        ),
    )

    resumo = await service.get_summary(user_id, _INICIO, _FIM)

    assert resumo.total_expenses == Decimal("30.00")


@pytest.mark.asyncio
async def test_transacoes_fora_do_periodo_nao_entram() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("10.00"),
            transaction_date=date(2026, 6, 30),
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("20.00"),
            transaction_date=date(2026, 8, 1),
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("5.00"),
            transaction_date=date(2026, 7, 15),
        ),
    )

    resumo = await service.get_summary(user_id, _INICIO, _FIM)

    assert resumo.total_expenses == Decimal("5.00")
