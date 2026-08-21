"""Escrita e relatórios de transações (RF-30 a RF-32, RF-38 a RF-40, RF-50 a RF-58)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TypedDict

from app.domain.enums import TransactionSource, TransactionType
from app.domain.errors import DomainError
from app.domain.money import Money, to_money
from app.domain.repositories import CategoryRepository, TransactionRepository
from app.domain.text import normalize_text
from app.models.category import Category
from app.models.transaction import Transaction

_CATEGORIA_PADRAO_FALLBACK = "Outros"


@dataclass(frozen=True)
class CreateTransactionResult:
    """`needs_category=True` sinaliza ao agente que ele deve perguntar a categoria (RN-03)."""

    transaction: Transaction
    needs_category: bool = False


@dataclass(frozen=True)
class FinanceSummary:
    total_expenses: Money
    total_income: Money
    balance: Money


class CategorySpending(TypedDict):
    """Uma linha do agrupamento de `get_spending_by_category` (RF-53)."""

    category: str
    total: Money
    percent: float
    count: int


@dataclass(frozen=True)
class PeriodComparison:
    """`percent_change=None` quando o período anterior é zero — não dá pra calcular variação
    percentual a partir de uma base zero (RF-55)."""

    current_total: Money
    previous_total: Money
    absolute_change: Money
    percent_change: float | None


@dataclass(frozen=True)
class MonthlyTotal:
    """Uma linha da série de `get_monthly_trend` (RF-58) — inclui meses sem movimento."""

    year: int
    month: int
    total: Money


class FinanceService:
    def __init__(
        self,
        transaction_repository: TransactionRepository,
        category_repository: CategoryRepository,
    ) -> None:
        self._transaction_repository = transaction_repository
        self._category_repository = category_repository

    async def create_transaction(
        self,
        user_id: uuid.UUID,
        *,
        transaction_type: TransactionType,
        amount: Decimal,
        currency: str,
        source: TransactionSource,
        today: date,
        transaction_date: date | None = None,
        description: str | None = None,
        category_id: uuid.UUID | None = None,
        payment_method: str | None = None,
    ) -> CreateTransactionResult:
        valor = _validar_valor(amount)

        needs_category = False
        if category_id is not None:
            await self._exigir_categoria_do_usuario(user_id, category_id)
        else:
            categoria_outros = await self._find_categoria_outros(user_id, transaction_type)
            category_id = categoria_outros.id if categoria_outros is not None else None
            needs_category = True

        transacao = Transaction(
            id=uuid.uuid4(),
            user_id=user_id,
            type=transaction_type,
            amount=valor,
            currency=currency,  # RN-11: guardada como veio, sem conversão no MVP
            description=description,
            category_id=category_id,
            date=transaction_date or today,  # RN-02
            payment_method=payment_method,
            source=source,
        )
        persistida = await self._transaction_repository.add(user_id, transacao)
        return CreateTransactionResult(transaction=persistida, needs_category=needs_category)

    async def update_transaction(
        self,
        user_id: uuid.UUID,
        transaction_id: uuid.UUID,
        *,
        amount: Decimal | None = None,
        transaction_date: date | None = None,
        category_id: uuid.UUID | None = None,
        description: str | None = None,
    ) -> Transaction | None:
        changes: dict[str, object] = {}
        if amount is not None:
            changes["amount"] = _validar_valor(amount)
        if transaction_date is not None:
            changes["date"] = transaction_date
        if category_id is not None:
            await self._exigir_categoria_do_usuario(user_id, category_id)
            changes["category_id"] = category_id
        if description is not None:
            changes["description"] = description

        if not changes:
            return await self._transaction_repository.get(user_id, transaction_id)
        return await self._transaction_repository.update(user_id, transaction_id, **changes)

    async def delete_transaction(self, user_id: uuid.UUID, transaction_id: uuid.UUID) -> bool:
        return await self._transaction_repository.delete(user_id, transaction_id)

    async def get_summary(
        self, user_id: uuid.UUID, start_date: date, end_date: date
    ) -> FinanceSummary:
        """RF-50 a RF-52: total de despesas, de receitas e o saldo (pode ser negativo)."""
        transacoes = await self._transactions_no_periodo(user_id, start_date, end_date)
        despesas = _somar(t.amount for t in transacoes if t.type == TransactionType.EXPENSE)
        receitas = _somar(t.amount for t in transacoes if t.type == TransactionType.INCOME)
        return FinanceSummary(
            total_expenses=to_money(despesas),
            total_income=to_money(receitas),
            balance=to_money(receitas - despesas),
        )

    async def get_spending_by_category(
        self, user_id: uuid.UUID, start_date: date, end_date: date
    ) -> list[CategorySpending]:
        """RF-53: despesas do período agrupadas por categoria, com total e percentual."""
        transacoes = await self._transactions_no_periodo(
            user_id, start_date, end_date, TransactionType.EXPENSE
        )
        total_geral = _somar(t.amount for t in transacoes)

        por_categoria: dict[uuid.UUID | None, list[Transaction]] = {}
        for transacao in transacoes:
            por_categoria.setdefault(transacao.category_id, []).append(transacao)

        nomes_por_id: dict[uuid.UUID | None, str] = {
            categoria.id: categoria.name
            for categoria in await self._category_repository.list_by_user(user_id)
        }

        resultado: list[CategorySpending] = []
        for category_id, itens in por_categoria.items():
            subtotal = to_money(_somar(t.amount for t in itens))
            resultado.append(
                CategorySpending(
                    category=nomes_por_id.get(category_id, _CATEGORIA_PADRAO_FALLBACK),
                    total=subtotal,
                    percent=round(float(subtotal / total_geral * 100), 1),
                    count=len(itens),
                )
            )
        resultado.sort(key=lambda item: item["total"], reverse=True)
        return resultado

    async def get_category_spending(
        self, user_id: uuid.UUID, start_date: date, end_date: date, category_id: uuid.UUID
    ) -> Money:
        """RF-54: total gasto numa categoria específica dentro do período."""
        transacoes = await self._transactions_no_periodo(
            user_id, start_date, end_date, TransactionType.EXPENSE
        )
        return to_money(_somar(t.amount for t in transacoes if t.category_id == category_id))

    async def compare_periods(
        self,
        user_id: uuid.UUID,
        *,
        current_start: date,
        current_end: date,
        previous_start: date,
        previous_end: date,
        transaction_type: TransactionType = TransactionType.EXPENSE,
    ) -> PeriodComparison:
        """RF-55: total do período atual vs. o anterior, com variação absoluta e percentual."""
        atual = to_money(
            _somar(
                t.amount
                for t in await self._transactions_no_periodo(
                    user_id, current_start, current_end, transaction_type
                )
            )
        )
        anterior = to_money(
            _somar(
                t.amount
                for t in await self._transactions_no_periodo(
                    user_id, previous_start, previous_end, transaction_type
                )
            )
        )
        percentual = None if anterior == 0 else round(float((atual - anterior) / anterior * 100), 1)
        return PeriodComparison(
            current_total=atual,
            previous_total=anterior,
            absolute_change=to_money(atual - anterior),
            percent_change=percentual,
        )

    async def list_transactions(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        *,
        category_id: uuid.UUID | None = None,
        transaction_type: TransactionType | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        text: str | None = None,
    ) -> list[Transaction]:
        """RF-56: listagem do período com filtros por categoria, tipo, valor e texto."""
        transacoes = await self._transactions_no_periodo(
            user_id, start_date, end_date, transaction_type
        )
        if category_id is not None:
            transacoes = [t for t in transacoes if t.category_id == category_id]
        if min_amount is not None:
            transacoes = [t for t in transacoes if t.amount >= min_amount]
        if max_amount is not None:
            transacoes = [t for t in transacoes if t.amount <= max_amount]
        if text is not None:
            alvo = normalize_text(text)
            transacoes = [
                t
                for t in transacoes
                if t.description is not None and alvo in normalize_text(t.description)
            ]
        return transacoes

    async def get_top_expenses(
        self, user_id: uuid.UUID, start_date: date, end_date: date, n: int
    ) -> list[Transaction]:
        """RF-57: as `n` maiores despesas do período — ou menos, se não houver `n`."""
        transacoes = await self._transactions_no_periodo(
            user_id, start_date, end_date, TransactionType.EXPENSE
        )
        return sorted(transacoes, key=lambda t: t.amount, reverse=True)[:n]

    async def get_monthly_trend(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        transaction_type: TransactionType = TransactionType.EXPENSE,
    ) -> list[MonthlyTotal]:
        """RF-58: série mensal do período — meses sem movimento entram com zero."""
        transacoes = await self._transactions_no_periodo(
            user_id, start_date, end_date, transaction_type
        )
        totais_por_mes: dict[tuple[int, int], Decimal] = {}
        for transacao in transacoes:
            chave = (transacao.date.year, transacao.date.month)
            totais_por_mes[chave] = totais_por_mes.get(chave, Decimal("0")) + transacao.amount

        return [
            MonthlyTotal(
                year=ano, month=mes, total=to_money(totais_por_mes.get((ano, mes), Decimal("0")))
            )
            for ano, mes in _meses_no_periodo(start_date, end_date)
        ]

    async def _transactions_no_periodo(
        self,
        user_id: uuid.UUID,
        start_date: date,
        end_date: date,
        transaction_type: TransactionType | None = None,
    ) -> list[Transaction]:
        todas = await self._transaction_repository.list_by_user(user_id)
        return [
            transacao
            for transacao in todas
            if start_date <= transacao.date <= end_date
            and (transaction_type is None or transacao.type == transaction_type)
        ]

    async def _find_categoria_outros(
        self, user_id: uuid.UUID, transaction_type: TransactionType
    ) -> Category | None:
        categorias = await self._category_repository.list_by_user(user_id)
        for categoria in categorias:
            if (
                categoria.name == _CATEGORIA_PADRAO_FALLBACK
                and categoria.type == transaction_type
                and categoria.is_active
            ):
                return categoria
        return None

    async def _exigir_categoria_do_usuario(
        self, user_id: uuid.UUID, category_id: uuid.UUID
    ) -> None:
        """RNF-04: uma transação nunca pode referenciar a categoria de outro usuário."""
        categoria = await self._category_repository.get(user_id, category_id)
        if categoria is None:
            raise DomainError("Categoria não encontrada para este usuário")


def _validar_valor(amount: Decimal) -> Money:
    """RN-04: valores negativos ou zero são rejeitados; o sinal vem do campo `type`."""
    valor = to_money(amount)
    if valor <= 0:
        raise DomainError("O valor da transação deve ser maior que zero")
    return valor


def _somar(valores: Iterable[Decimal]) -> Decimal:
    return sum(valores, start=Decimal("0"))


def _meses_no_periodo(start_date: date, end_date: date) -> list[tuple[int, int]]:
    meses: list[tuple[int, int]] = []
    ano, mes = start_date.year, start_date.month
    while (ano, mes) <= (end_date.year, end_date.month):
        meses.append((ano, mes))
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
    return meses
