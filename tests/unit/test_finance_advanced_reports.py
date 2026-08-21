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


def _nova_transacao(
    user_id: uuid.UUID,
    *,
    transaction_type: TransactionType = TransactionType.EXPENSE,
    amount: Decimal,
    transaction_date: date,
    category_id: uuid.UUID | None = None,
    description: str | None = None,
) -> Transaction:
    return Transaction(
        id=uuid.uuid4(),
        user_id=user_id,
        type=transaction_type,
        amount=amount,
        currency="BRL",
        category_id=category_id,
        date=transaction_date,
        description=description,
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
async def test_comparacao_entre_dois_periodos_com_variacao_absoluta_e_percentual() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(user_id, amount=Decimal("100.00"), transaction_date=date(2026, 6, 15)),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(user_id, amount=Decimal("150.00"), transaction_date=date(2026, 7, 15)),
    )

    comparacao = await service.compare_periods(
        user_id,
        current_start=date(2026, 7, 1),
        current_end=date(2026, 7, 31),
        previous_start=date(2026, 6, 1),
        previous_end=date(2026, 6, 30),
    )

    assert comparacao.current_total == Decimal("150.00")
    assert comparacao.previous_total == Decimal("100.00")
    assert comparacao.absolute_change == Decimal("50.00")
    assert comparacao.percent_change == 50.0


@pytest.mark.asyncio
async def test_comparacao_quando_periodo_anterior_e_zero_sem_divisao_por_zero() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(user_id, amount=Decimal("100.00"), transaction_date=date(2026, 7, 15)),
    )

    comparacao = await service.compare_periods(
        user_id,
        current_start=date(2026, 7, 1),
        current_end=date(2026, 7, 31),
        previous_start=date(2026, 6, 1),
        previous_end=date(2026, 6, 30),
    )

    assert comparacao.current_total == Decimal("100.00")
    assert comparacao.previous_total == Decimal("0.00")
    assert comparacao.absolute_change == Decimal("100.00")
    assert comparacao.percent_change is None


@pytest.mark.asyncio
async def test_listagem_com_filtro_por_categoria_tipo_faixa_de_valor_e_texto() -> None:
    service, transaction_repo, category_repo = _novo_service()
    user_id = uuid.uuid4()
    mercado = await category_repo.add(user_id, _nova_categoria(user_id, "Mercado"))
    lazer = await category_repo.add(user_id, _nova_categoria(user_id, "Lazer"))

    alvo = await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            amount=Decimal("50.00"),
            transaction_date=date(2026, 7, 10),
            category_id=mercado.id,
            description="Compras da semana",
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            amount=Decimal("50.00"),
            transaction_date=date(2026, 7, 11),
            category_id=lazer.id,
            description="Cinema",
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("50.00"),
            transaction_date=date(2026, 7, 12),
            category_id=mercado.id,
            description="Compras reembolsadas",
        ),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            amount=Decimal("500.00"),
            transaction_date=date(2026, 7, 13),
            category_id=mercado.id,
            description="Compras do mês",
        ),
    )

    resultado = await service.list_transactions(
        user_id,
        date(2026, 7, 1),
        date(2026, 7, 31),
        category_id=mercado.id,
        transaction_type=TransactionType.EXPENSE,
        min_amount=Decimal("10.00"),
        max_amount=Decimal("100.00"),
        text="compras",
    )

    assert [transacao.id for transacao in resultado] == [alvo.id]


@pytest.mark.asyncio
async def test_busca_textual_ignora_acentos_e_maiusculas() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(
            user_id,
            amount=Decimal("30.00"),
            transaction_date=date(2026, 7, 10),
            description="Almoço no trabalho",
        ),
    )

    resultado = await service.list_transactions(
        user_id, date(2026, 7, 1), date(2026, 7, 31), text="almoco"
    )

    assert len(resultado) == 1


@pytest.mark.asyncio
async def test_top_n_devolve_exatamente_n_ordenado_corretamente() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    for valor, dia in [("30.00", 1), ("90.00", 2), ("10.00", 3), ("50.00", 4)]:
        await transaction_repo.add(
            user_id,
            _nova_transacao(user_id, amount=Decimal(valor), transaction_date=date(2026, 7, dia)),
        )

    top = await service.get_top_expenses(user_id, date(2026, 7, 1), date(2026, 7, 31), 2)

    assert [transacao.amount for transacao in top] == [Decimal("90.00"), Decimal("50.00")]


@pytest.mark.asyncio
async def test_top_n_com_menos_de_n_transacoes_devolve_o_que_existe() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(user_id, amount=Decimal("20.00"), transaction_date=date(2026, 7, 1)),
    )

    top = await service.get_top_expenses(user_id, date(2026, 7, 1), date(2026, 7, 31), 5)

    assert len(top) == 1


@pytest.mark.asyncio
async def test_serie_mensal_preenche_meses_sem_movimento_com_zero() -> None:
    service, transaction_repo, _ = _novo_service()
    user_id = uuid.uuid4()
    await transaction_repo.add(
        user_id,
        _nova_transacao(user_id, amount=Decimal("100.00"), transaction_date=date(2026, 5, 10)),
    )
    await transaction_repo.add(
        user_id,
        _nova_transacao(user_id, amount=Decimal("200.00"), transaction_date=date(2026, 7, 10)),
    )

    serie = await service.get_monthly_trend(user_id, date(2026, 5, 1), date(2026, 7, 31))

    assert [(item.year, item.month, item.total) for item in serie] == [
        (2026, 5, Decimal("100.00")),
        (2026, 6, Decimal("0.00")),
        (2026, 7, Decimal("200.00")),
    ]
