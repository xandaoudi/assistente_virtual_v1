"""Tools de escrita sobre o `FinanceService` (T2.5, RF-85 a RF-89, CA-13).

`ToolRegistry` recebe os repositórios já prontos (produção: SQLAlchemy; testes: em
memória — RNF-33) e expõe as funções de tool com a assinatura `(ctx, params)`. Nenhum
método aceita exceção crua: tudo passa por `run_safely` ou é traduzido explicitamente
para o envelope do T2.1 antes de sair daqui.
"""

import uuid
from datetime import date as date_type
from decimal import Decimal

from app.domain.category_service import CategoryService
from app.domain.enums import TransactionSource, TransactionType
from app.domain.errors import DomainError
from app.domain.finance_service import FinanceService
from app.domain.money import parse_amount, to_money
from app.domain.periods import resolve_period
from app.domain.repositories import (
    CategoryRepository,
    ToolAuditLogRepository,
    TransactionRepository,
    UserRepository,
)
from app.domain.text import normalize_text
from app.models.category import Category
from app.models.transaction import Transaction
from app.tools.audit import audited
from app.tools.context import ToolContext
from app.tools.results import ErrorCode, ToolError, ToolResult, ToolSuccess, run_safely
from app.tools.schemas import (
    CategorySpendingItem,
    CategoryView,
    ComparePeriodsParams,
    ComparePeriodsResult,
    CreateCategoryParams,
    CreateCategoryResult,
    CreateTransactionParams,
    CreateTransactionResult,
    DeleteTransactionParams,
    DeleteTransactionResult,
    GetCategorySpendingParams,
    GetCategorySpendingResult,
    GetMonthlyTrendParams,
    GetSpendingByCategoryParams,
    GetSummaryParams,
    GetSummaryResult,
    GetTopExpensesParams,
    GetUserPreferencesParams,
    ListCategoriesParams,
    ListTransactionsParams,
    ListTransactionsResult,
    MonthlyTotalItem,
    PaymentMethod,
    ResolveRelativeDateParams,
    ResolveRelativeDateResult,
    TransactionView,
    UpdateTransactionParams,
    UpdateTransactionResult,
    UpdateUserPreferencesParams,
    UserPreferencesResult,
)

_TRANSACAO_NAO_ENCONTRADA = "Transação não encontrada."
_GROUP_BY_NAO_SUPORTADO = "group_by ainda não é suportado por compare_periods."
_SUGESTAO_EXPRESSOES_PERIODO = (
    'Expressões aceitas: "hoje", "ontem", "esta semana", "semana passada", "este mês", '
    '"mês passado", "últimos 30 dias", "este ano", "no ano passado", "em <mês>" '
    '(opcionalmente "de <ano>").'
)


def _categoria_por_nome(categorias: list[Category], nome: str) -> Category | None:
    alvo = normalize_text(nome)
    for categoria in categorias:
        if categoria.is_active and normalize_text(categoria.name) == alvo:
            return categoria
    return None


def _nome_por_id(categorias: list[Category], category_id: uuid.UUID | None) -> str | None:
    if category_id is None:
        return None
    for categoria in categorias:
        if categoria.id == category_id:
            return categoria.name
    return None


def _resolver_categoria_id(categorias: list[Category], nome: str | None) -> uuid.UUID | None:
    """`None` quando `nome` também é `None` — categoria será decidida pelo domínio (RN-03).

    Levanta `DomainError` quando um nome foi dado mas não corresponde a nenhuma categoria
    ativa do usuário: diferente de omitir a categoria, um nome explicado errado não deve
    ser silenciosamente ignorado.
    """
    if nome is None:
        return None
    encontrada = _categoria_por_nome(categorias, nome)
    if encontrada is None:
        raise DomainError(f'Categoria "{nome}" não encontrada.')
    return encontrada.id


def _payment_method_de(valor: str | None) -> PaymentMethod | None:
    if valor is None:
        return None
    try:
        return PaymentMethod(valor)
    except ValueError:
        return None


def _transaction_view(transacao: Transaction, categorias: list[Category]) -> TransactionView:
    return TransactionView(
        transaction_id=transacao.id,
        type=transacao.type,
        amount=transacao.amount,
        description=transacao.description or "",
        date=transacao.date,
        category=_nome_por_id(categorias, transacao.category_id),
        payment_method=_payment_method_de(transacao.payment_method),
    )


def _inicio_de_n_meses_atras(referencia: date_type, months: int) -> date_type:
    """Primeiro dia do mês que inicia uma janela de `months` meses terminando em `referencia`."""
    indice_mes = referencia.year * 12 + (referencia.month - 1) - (months - 1)
    ano, mes = divmod(indice_mes, 12)
    return date_type(ano, mes + 1, 1)


class ToolRegistry:
    def __init__(
        self,
        transaction_repository: TransactionRepository,
        category_repository: CategoryRepository,
        user_repository: UserRepository,
        audit_log_repository: ToolAuditLogRepository,
    ) -> None:
        self._category_repository = category_repository
        self._user_repository = user_repository
        self._audit_log_repository = audit_log_repository
        self._finance_service = FinanceService(transaction_repository, category_repository)
        self._category_service = CategoryService(category_repository)

    @audited("create_transaction")
    async def create_transaction(
        self, ctx: ToolContext, params: CreateTransactionParams
    ) -> ToolResult[CreateTransactionResult]:
        parsed = parse_amount(params.amount)
        if parsed.ambiguous:
            return ToolError(
                code=ErrorCode.AMBIGUOUS_INPUT,
                message=f'O valor "{params.amount}" é ambíguo — confirme com o usuário.',
                detail={"amount_text": params.amount},
            )

        resultado = await run_safely(self._criar_no_dominio(ctx, params, parsed.amount))
        if isinstance(resultado, ToolError):
            return resultado

        transacao, nome_categoria = resultado.data
        return ToolSuccess(
            data=CreateTransactionResult(
                transaction_id=transacao.id,
                type=transacao.type,
                amount=transacao.amount,
                description=transacao.description or "",
                date=transacao.date,
                category=nome_categoria,
                payment_method=_payment_method_de(transacao.payment_method),
                category_confidence=None,
            )
        )

    async def _criar_no_dominio(
        self, ctx: ToolContext, params: CreateTransactionParams, amount: Decimal
    ) -> tuple[Transaction, str | None]:
        categorias = await self._category_repository.list_by_user(ctx.user_id)
        category_id = _resolver_categoria_id(categorias, params.category)

        criada = await self._finance_service.create_transaction(
            ctx.user_id,
            transaction_type=params.type,
            amount=amount,
            currency=ctx.currency,
            source=TransactionSource.CHAT,
            today=ctx.today,
            transaction_date=params.date,
            description=params.description,
            category_id=category_id,
            payment_method=params.payment_method.value if params.payment_method else None,
            idempotency_key=ctx.idempotency_key,
        )
        nome = _nome_por_id(categorias, criada.transaction.category_id)
        return criada.transaction, nome

    @audited("update_transaction")
    async def update_transaction(
        self, ctx: ToolContext, params: UpdateTransactionParams
    ) -> ToolResult[UpdateTransactionResult]:
        amount: Decimal | None = None
        if params.amount is not None:
            parsed = parse_amount(params.amount)
            if parsed.ambiguous:
                return ToolError(
                    code=ErrorCode.AMBIGUOUS_INPUT,
                    message=f'O valor "{params.amount}" é ambíguo — confirme com o usuário.',
                    detail={"amount_text": params.amount},
                )
            amount = parsed.amount

        resultado = await run_safely(self._atualizar_no_dominio(ctx, params, amount))
        if isinstance(resultado, ToolError):
            return resultado
        if resultado.data is None:
            return ToolError(code=ErrorCode.NOT_FOUND, message=_TRANSACAO_NAO_ENCONTRADA)

        transacao, nome_categoria = resultado.data
        return ToolSuccess(
            data=UpdateTransactionResult(
                transaction_id=transacao.id,
                type=transacao.type,
                amount=transacao.amount,
                description=transacao.description or "",
                date=transacao.date,
                category=nome_categoria,
                payment_method=_payment_method_de(transacao.payment_method),
            )
        )

    async def _atualizar_no_dominio(
        self, ctx: ToolContext, params: UpdateTransactionParams, amount: Decimal | None
    ) -> tuple[Transaction, str | None] | None:
        categorias = await self._category_repository.list_by_user(ctx.user_id)
        category_id = _resolver_categoria_id(categorias, params.category)

        atualizada = await self._finance_service.update_transaction(
            ctx.user_id,
            params.transaction_id,
            amount=amount,
            transaction_date=params.date,
            category_id=category_id,
            description=params.description,
        )
        if atualizada is None:
            return None
        nome = _nome_por_id(categorias, atualizada.category_id)
        return atualizada, nome

    @audited("delete_transaction")
    async def delete_transaction(
        self, ctx: ToolContext, params: DeleteTransactionParams
    ) -> ToolResult[DeleteTransactionResult]:
        resultado = await run_safely(
            self._finance_service.delete_transaction(ctx.user_id, params.transaction_id)
        )
        if isinstance(resultado, ToolError):
            return resultado
        if not resultado.data:
            return ToolError(code=ErrorCode.NOT_FOUND, message=_TRANSACAO_NAO_ENCONTRADA)

        return ToolSuccess(
            data=DeleteTransactionResult(transaction_id=params.transaction_id, deleted=True)
        )

    @audited("get_summary")
    async def get_summary(
        self, ctx: ToolContext, params: GetSummaryParams
    ) -> ToolResult[GetSummaryResult]:
        resultado = await run_safely(
            self._finance_service.get_summary(ctx.user_id, params.start_date, params.end_date)
        )
        if isinstance(resultado, ToolError):
            return resultado

        resumo = resultado.data
        return ToolSuccess(
            data=GetSummaryResult(
                total_expenses=resumo.total_expenses,
                total_income=resumo.total_income,
                balance=resumo.balance,
                transaction_count=resumo.transaction_count,
            )
        )

    @audited("get_spending_by_category")
    async def get_spending_by_category(
        self, ctx: ToolContext, params: GetSpendingByCategoryParams
    ) -> ToolResult[list[CategorySpendingItem]]:
        tipo = params.type or TransactionType.EXPENSE
        resultado = await run_safely(
            self._finance_service.get_spending_by_category(
                ctx.user_id, params.start_date, params.end_date, transaction_type=tipo
            )
        )
        if isinstance(resultado, ToolError):
            return resultado

        return ToolSuccess(
            data=[
                CategorySpendingItem(
                    category=item["category"],
                    total=item["total"],
                    percent=item["percent"],
                    count=item["count"],
                )
                for item in resultado.data
            ]
        )

    @audited("get_category_spending")
    async def get_category_spending(
        self, ctx: ToolContext, params: GetCategorySpendingParams
    ) -> ToolResult[GetCategorySpendingResult]:
        return await run_safely(self._get_category_spending_no_dominio(ctx, params))

    async def _get_category_spending_no_dominio(
        self, ctx: ToolContext, params: GetCategorySpendingParams
    ) -> GetCategorySpendingResult:
        categorias = await self._category_repository.list_by_user(ctx.user_id)
        categoria = _categoria_por_nome(categorias, params.category)
        if categoria is None:
            raise DomainError(f'Categoria "{params.category}" não encontrada.')

        total = await self._finance_service.get_category_spending(
            ctx.user_id, params.start_date, params.end_date, categoria.id
        )
        transacoes = await self._finance_service.list_transactions(
            ctx.user_id,
            params.start_date,
            params.end_date,
            category_id=categoria.id,
            transaction_type=TransactionType.EXPENSE,
        )
        count = len(transacoes)
        average = to_money(total / count) if count > 0 else Decimal("0.00")
        return GetCategorySpendingResult(total=total, count=count, average=average)

    @audited("list_transactions")
    async def list_transactions(
        self, ctx: ToolContext, params: ListTransactionsParams
    ) -> ToolResult[ListTransactionsResult]:
        resultado = await run_safely(self._listar_no_dominio(ctx, params))
        if isinstance(resultado, ToolError):
            return resultado

        transacoes, categorias = resultado.data
        truncado = params.limit is not None and len(transacoes) > params.limit
        if params.limit is not None:
            transacoes = transacoes[: params.limit]

        return ToolSuccess(
            data=ListTransactionsResult(
                items=[_transaction_view(t, categorias) for t in transacoes],
                truncated=truncado,
            )
        )

    async def _listar_no_dominio(
        self, ctx: ToolContext, params: ListTransactionsParams
    ) -> tuple[list[Transaction], list[Category]]:
        categorias = await self._category_repository.list_by_user(ctx.user_id)
        category_id = _resolver_categoria_id(categorias, params.category)

        transacoes = await self._finance_service.list_transactions(
            ctx.user_id,
            params.start_date,
            params.end_date,
            category_id=category_id,
            transaction_type=params.type,
            min_amount=params.min_amount,
            max_amount=params.max_amount,
            text=params.query,
        )
        transacoes = sorted(transacoes, key=lambda t: t.date, reverse=True)
        return transacoes, categorias

    @audited("compare_periods")
    async def compare_periods(
        self, ctx: ToolContext, params: ComparePeriodsParams
    ) -> ToolResult[ComparePeriodsResult]:
        if params.group_by is not None:
            return ToolError(code=ErrorCode.VALIDATION_ERROR, message=_GROUP_BY_NAO_SUPORTADO)

        resultado = await run_safely(
            self._finance_service.compare_periods(
                ctx.user_id,
                current_start=params.period_a_start,
                current_end=params.period_a_end,
                previous_start=params.period_b_start,
                previous_end=params.period_b_end,
            )
        )
        if isinstance(resultado, ToolError):
            return resultado

        comparacao = resultado.data
        return ToolSuccess(
            data=ComparePeriodsResult(
                period_a_total=comparacao.current_total,
                period_b_total=comparacao.previous_total,
                absolute_change=comparacao.absolute_change,
                percent_change=comparacao.percent_change,
            )
        )

    @audited("get_top_expenses")
    async def get_top_expenses(
        self, ctx: ToolContext, params: GetTopExpensesParams
    ) -> ToolResult[list[TransactionView]]:
        resultado = await run_safely(self._top_expenses_no_dominio(ctx, params))
        if isinstance(resultado, ToolError):
            return resultado

        transacoes, categorias = resultado.data
        return ToolSuccess(data=[_transaction_view(t, categorias) for t in transacoes])

    async def _top_expenses_no_dominio(
        self, ctx: ToolContext, params: GetTopExpensesParams
    ) -> tuple[list[Transaction], list[Category]]:
        categorias = await self._category_repository.list_by_user(ctx.user_id)
        transacoes = await self._finance_service.get_top_expenses(
            ctx.user_id, params.start_date, params.end_date, params.limit
        )
        return transacoes, categorias

    @audited("get_monthly_trend")
    async def get_monthly_trend(
        self, ctx: ToolContext, params: GetMonthlyTrendParams
    ) -> ToolResult[list[MonthlyTotalItem]]:
        inicio = _inicio_de_n_meses_atras(ctx.today, params.months)
        resultado = await run_safely(
            self._finance_service.get_monthly_trend(ctx.user_id, inicio, ctx.today)
        )
        if isinstance(resultado, ToolError):
            return resultado

        return ToolSuccess(
            data=[
                MonthlyTotalItem(year=item.year, month=item.month, total=item.total)
                for item in resultado.data
            ]
        )

    @audited("list_categories")
    async def list_categories(
        self, ctx: ToolContext, params: ListCategoriesParams
    ) -> ToolResult[list[CategoryView]]:
        resultado = await run_safely(
            self._category_service.list_categories(ctx.user_id, category_type=params.type)
        )
        if isinstance(resultado, ToolError):
            return resultado

        return ToolSuccess(data=[CategoryView(name=c.name, type=c.type) for c in resultado.data])

    @audited("create_category")
    async def create_category(
        self, ctx: ToolContext, params: CreateCategoryParams
    ) -> ToolResult[CreateCategoryResult]:
        resultado = await run_safely(self._criar_categoria_no_dominio(ctx, params))
        if isinstance(resultado, ToolError):
            return resultado

        categoria = resultado.data
        return ToolSuccess(data=CreateCategoryResult(name=categoria.name, type=categoria.type))

    async def _criar_categoria_no_dominio(
        self, ctx: ToolContext, params: CreateCategoryParams
    ) -> Category:
        categorias = await self._category_repository.list_by_user(ctx.user_id)
        alvo = normalize_text(params.name)
        for categoria in categorias:
            if (
                categoria.is_active
                and categoria.type == params.type
                and (normalize_text(categoria.name) == alvo)
            ):
                raise DomainError(f'Categoria "{params.name}" já existe.')

        return await self._category_service.create_category(ctx.user_id, params.name, params.type)

    @audited("get_user_preferences")
    async def get_user_preferences(
        self, ctx: ToolContext, _params: GetUserPreferencesParams
    ) -> ToolResult[UserPreferencesResult]:
        resultado = await run_safely(self._user_repository.get(ctx.user_id))
        if isinstance(resultado, ToolError):
            return resultado
        if resultado.data is None:
            return ToolError(code=ErrorCode.NOT_FOUND, message="Usuário não encontrado.")

        user = resultado.data
        return ToolSuccess(
            data=UserPreferencesResult(
                timezone=user.timezone, currency=user.currency, locale=user.locale
            )
        )

    @audited("update_user_preferences")
    async def update_user_preferences(
        self, ctx: ToolContext, params: UpdateUserPreferencesParams
    ) -> ToolResult[UserPreferencesResult]:
        changes = params.model_dump(exclude_none=True)
        if not changes:
            return await self.get_user_preferences(ctx, GetUserPreferencesParams())

        resultado = await run_safely(self._user_repository.update(ctx.user_id, **changes))
        if isinstance(resultado, ToolError):
            return resultado
        if resultado.data is None:
            return ToolError(code=ErrorCode.NOT_FOUND, message="Usuário não encontrado.")

        user = resultado.data
        return ToolSuccess(
            data=UserPreferencesResult(
                timezone=user.timezone, currency=user.currency, locale=user.locale
            )
        )

    @audited("resolve_relative_date")
    async def resolve_relative_date(
        self, ctx: ToolContext, params: ResolveRelativeDateParams
    ) -> ToolResult[ResolveRelativeDateResult]:
        referencia = params.reference_date or ctx.today
        try:
            inicio, fim = resolve_period(params.expression, referencia)
        except DomainError as exc:
            return ToolError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"{exc} {_SUGESTAO_EXPRESSOES_PERIODO}",
            )
        except Exception:
            return ToolError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Erro interno inesperado. Tente novamente mais tarde.",
            )

        return ToolSuccess(data=ResolveRelativeDateResult(start_date=inicio, end_date=fim))
