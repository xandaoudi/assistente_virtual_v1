"""Prova de isolamento entre usuários (CA-12, RNF-04) — arquivo dedicado e impossível de ignorar.

Cenário comum aos testes: dois usuários, cada um com categorias e transações próprias,
cobrindo o mesmo período e com descrições parecidas — o cenário onde vazamento é mais fácil
de acontecer sem ninguém notar.
"""

import inspect
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.db import get_session_maker
from app.domain.category_service import CategoryService
from app.domain.enums import TransactionSource, TransactionType
from app.domain.finance_service import FinanceService, MonthlyTotal
from app.domain.user_service import UserService
from app.models.user import User
from app.repositories.sqlalchemy import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyTransactionRepository,
)

pytestmark = pytest.mark.integration

_INICIO = date(2026, 7, 1)
_FIM = date(2026, 7, 31)


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
            await session.delete(user)  # ON DELETE CASCADE remove categorias/transações junto
            await session.commit()


def _novos_servicos() -> tuple[FinanceService, CategoryService]:
    category_repo = SqlAlchemyCategoryRepository()
    transaction_repo = SqlAlchemyTransactionRepository()
    return FinanceService(transaction_repo, category_repo), CategoryService(category_repo)


@pytest.mark.asyncio
async def test_nenhum_relatorio_vaza_dados_entre_dois_usuarios() -> None:
    finance, categories = _novos_servicos()
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    try:
        mercado_a = await categories.create_category(user_a, "Mercado", TransactionType.EXPENSE)
        mercado_b = await categories.create_category(user_b, "Mercado", TransactionType.EXPENSE)

        for valor, dia in [(Decimal("100.00"), 5), (Decimal("50.00"), 15)]:
            await finance.create_transaction(
                user_a,
                transaction_type=TransactionType.EXPENSE,
                amount=valor,
                currency="BRL",
                source=TransactionSource.CHAT,
                today=_INICIO,
                transaction_date=date(2026, 7, dia),
                description="Compra no mercado",
                category_id=mercado_a.id,
            )
        await finance.create_transaction(
            user_a,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("1000.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_INICIO,
            transaction_date=date(2026, 7, 1),
        )

        # Valores bem distintos dos de A — se vazar, fica óbvio.
        for _ in range(3):
            await finance.create_transaction(
                user_b,
                transaction_type=TransactionType.EXPENSE,
                amount=Decimal("999.00"),
                currency="BRL",
                source=TransactionSource.CHAT,
                today=_INICIO,
                transaction_date=date(2026, 7, 10),
                description="Compra no mercado",
                category_id=mercado_b.id,
            )
        await finance.create_transaction(
            user_b,
            transaction_type=TransactionType.INCOME,
            amount=Decimal("5000.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_INICIO,
            transaction_date=date(2026, 7, 1),
        )

        resumo_a = await finance.get_summary(user_a, _INICIO, _FIM)
        assert resumo_a.total_expenses == Decimal("150.00")
        assert resumo_a.total_income == Decimal("1000.00")

        agrupado_a = await finance.get_spending_by_category(user_a, _INICIO, _FIM)
        assert len(agrupado_a) == 1
        assert agrupado_a[0]["total"] == Decimal("150.00")

        total_categoria_a = await finance.get_category_spending(user_a, _INICIO, _FIM, mercado_a.id)
        assert total_categoria_a == Decimal("150.00")

        comparacao_a = await finance.compare_periods(
            user_a,
            current_start=_INICIO,
            current_end=_FIM,
            previous_start=date(2026, 6, 1),
            previous_end=date(2026, 6, 30),
        )
        assert comparacao_a.current_total == Decimal("150.00")

        listagem_a = await finance.list_transactions(user_a, _INICIO, _FIM)
        assert all(t.amount != Decimal("999.00") for t in listagem_a)
        assert len(listagem_a) == 3

        top_a = await finance.get_top_expenses(user_a, _INICIO, _FIM, 10)
        assert all(t.amount != Decimal("999.00") for t in top_a)
        assert len(top_a) == 2

        tendencia_a = await finance.get_monthly_trend(user_a, _INICIO, _FIM)
        assert tendencia_a == [MonthlyTotal(year=2026, month=7, total=Decimal("150.00"))]

        resumo_b = await finance.get_summary(user_b, _INICIO, _FIM)
        assert resumo_b.total_expenses == Decimal("2997.00")
        assert resumo_b.total_income == Decimal("5000.00")
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)


@pytest.mark.asyncio
async def test_nenhuma_operacao_de_escrita_atinge_o_usuario_errado() -> None:
    finance, _ = _novos_servicos()
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    try:
        criada = await finance.create_transaction(
            user_a,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("80.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_INICIO,
            transaction_date=date(2026, 7, 5),
            description="Transação da usuária A",
        )
        transacao_id = criada.transaction.id

        resultado_update = await finance.update_transaction(
            user_b, transacao_id, amount=Decimal("1.00")
        )
        assert resultado_update is None

        resultado_delete = await finance.delete_transaction(user_b, transacao_id)
        assert resultado_delete is False

        intacta = await finance.list_transactions(user_a, _INICIO, _FIM)
        assert len(intacta) == 1
        assert intacta[0].amount == Decimal("80.00")
        assert intacta[0].deleted_at is None
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)


@pytest.mark.asyncio
async def test_categorias_homonimas_de_usuarios_distintos_nao_se_misturam_nos_agrupamentos() -> (
    None
):
    finance, categories = _novos_servicos()
    user_a = await _criar_usuario("Usuária A")
    user_b = await _criar_usuario("Usuário B")
    try:
        mercado_a = await categories.create_category(user_a, "Mercado", TransactionType.EXPENSE)
        mercado_b = await categories.create_category(user_b, "Mercado", TransactionType.EXPENSE)

        await finance.create_transaction(
            user_a,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("30.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_INICIO,
            transaction_date=date(2026, 7, 5),
            category_id=mercado_a.id,
        )
        await finance.create_transaction(
            user_b,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("70.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_INICIO,
            transaction_date=date(2026, 7, 5),
            category_id=mercado_b.id,
        )

        agrupado_a = await finance.get_spending_by_category(user_a, _INICIO, _FIM)
        agrupado_b = await finance.get_spending_by_category(user_b, _INICIO, _FIM)

        assert [item["total"] for item in agrupado_a if item["category"] == "Mercado"] == [
            Decimal("30.00")
        ]
        assert [item["total"] for item in agrupado_b if item["category"] == "Mercado"] == [
            Decimal("70.00")
        ]
    finally:
        await _remover_usuario(user_a)
        await _remover_usuario(user_b)


def test_todo_metodo_publico_do_finance_service_exige_user_id() -> None:
    """Protege o futuro: um método novo sem `user_id` reprova o build sozinho."""
    ofensores = [
        nome
        for nome, membro in inspect.getmembers(FinanceService, predicate=inspect.isfunction)
        if not nome.startswith("_") and "user_id" not in inspect.signature(membro).parameters
    ]
    assert ofensores == []
