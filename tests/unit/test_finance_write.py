import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domain.enums import TransactionSource, TransactionType
from app.domain.errors import DomainError
from app.domain.finance_service import FinanceService
from app.models.category import Category
from app.repositories.memory import InMemoryCategoryRepository, InMemoryTransactionRepository

pytestmark = pytest.mark.unit

_HOJE = date(2026, 8, 21)


def _novo_service() -> tuple[FinanceService, InMemoryCategoryRepository]:
    category_repo = InMemoryCategoryRepository()
    transaction_repo = InMemoryTransactionRepository()
    return FinanceService(transaction_repo, category_repo), category_repo


def _nova_categoria(
    user_id: uuid.UUID, name: str, category_type: TransactionType, *, is_default: bool = False
) -> Category:
    return Category(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        type=category_type,
        is_active=True,
        is_default=is_default,
    )


@pytest.mark.asyncio
async def test_criar_despesa_com_todos_os_campos() -> None:
    service, category_repo = _novo_service()
    user_id = uuid.uuid4()
    categoria = await category_repo.add(
        user_id, _nova_categoria(user_id, "Mercado", TransactionType.EXPENSE)
    )

    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("45.90"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
        transaction_date=date(2026, 8, 20),
        description="Almoço",
        category_id=categoria.id,
        payment_method="cartão",
    )

    transacao = resultado.transaction
    assert transacao.type == TransactionType.EXPENSE
    assert transacao.amount == Decimal("45.90")
    assert transacao.currency == "BRL"
    assert transacao.description == "Almoço"
    assert transacao.category_id == categoria.id
    assert transacao.date == date(2026, 8, 20)
    assert transacao.payment_method == "cartão"
    assert resultado.needs_category is False


@pytest.mark.asyncio
async def test_criar_receita() -> None:
    service, _ = _novo_service()
    user_id = uuid.uuid4()

    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.INCOME,
        amount=Decimal("3000.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )

    assert resultado.transaction.type == TransactionType.INCOME
    assert resultado.transaction.amount == Decimal("3000.00")


@pytest.mark.asyncio
async def test_sem_data_informada_usa_today() -> None:
    service, _ = _novo_service()
    user_id = uuid.uuid4()

    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )

    assert resultado.transaction.date == _HOJE


@pytest.mark.asyncio
async def test_valor_negativo_levanta_erro_de_dominio() -> None:
    service, _ = _novo_service()
    user_id = uuid.uuid4()

    with pytest.raises(DomainError):
        await service.create_transaction(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("-10.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_HOJE,
        )


@pytest.mark.asyncio
async def test_valor_zero_levanta_erro_de_dominio() -> None:
    service, _ = _novo_service()
    user_id = uuid.uuid4()

    with pytest.raises(DomainError):
        await service.create_transaction(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("0"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_HOJE,
        )


@pytest.mark.asyncio
async def test_sem_categoria_cai_em_outros_e_marca_needs_category() -> None:
    service, category_repo = _novo_service()
    user_id = uuid.uuid4()
    outros = await category_repo.add(
        user_id, _nova_categoria(user_id, "Outros", TransactionType.EXPENSE, is_default=True)
    )

    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("15.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )

    assert resultado.needs_category is True
    assert resultado.transaction.category_id == outros.id


@pytest.mark.asyncio
async def test_editar_valor_data_categoria_e_descricao() -> None:
    service, category_repo = _novo_service()
    user_id = uuid.uuid4()
    categoria = await category_repo.add(
        user_id, _nova_categoria(user_id, "Lazer", TransactionType.EXPENSE)
    )
    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("20.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
        category_id=categoria.id,
    )
    nova_categoria = await category_repo.add(
        user_id, _nova_categoria(user_id, "Saúde", TransactionType.EXPENSE)
    )

    atualizada = await service.update_transaction(
        user_id,
        resultado.transaction.id,
        amount=Decimal("99.90"),
        transaction_date=date(2026, 8, 1),
        category_id=nova_categoria.id,
        description="Consulta médica",
    )

    assert atualizada is not None
    assert atualizada.amount == Decimal("99.90")
    assert atualizada.date == date(2026, 8, 1)
    assert atualizada.category_id == nova_categoria.id
    assert atualizada.description == "Consulta médica"


@pytest.mark.asyncio
async def test_criar_transacao_com_categoria_de_outro_usuario_levanta_domain_error() -> None:
    service, category_repo = _novo_service()
    user_id = uuid.uuid4()
    outro_user_id = uuid.uuid4()
    categoria_de_outro = await category_repo.add(
        outro_user_id, _nova_categoria(outro_user_id, "Mercado", TransactionType.EXPENSE)
    )

    with pytest.raises(DomainError):
        await service.create_transaction(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            amount=Decimal("10.00"),
            currency="BRL",
            source=TransactionSource.CHAT,
            today=_HOJE,
            category_id=categoria_de_outro.id,
        )


@pytest.mark.asyncio
async def test_editar_transacao_com_categoria_de_outro_usuario_levanta_domain_error() -> None:
    service, category_repo = _novo_service()
    user_id = uuid.uuid4()
    outro_user_id = uuid.uuid4()
    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )
    categoria_de_outro = await category_repo.add(
        outro_user_id, _nova_categoria(outro_user_id, "Mercado", TransactionType.EXPENSE)
    )

    with pytest.raises(DomainError):
        await service.update_transaction(
            user_id, resultado.transaction.id, category_id=categoria_de_outro.id
        )


@pytest.mark.asyncio
async def test_categoria_outros_desativada_nao_e_usada_como_fallback() -> None:
    service, category_repo = _novo_service()
    user_id = uuid.uuid4()
    await category_repo.add(
        user_id,
        _nova_categoria(user_id, "Outros", TransactionType.EXPENSE, is_default=True),
    )
    desativada = await category_repo.update(
        user_id,
        (await category_repo.list_by_user(user_id))[0].id,
        is_active=False,
    )
    assert desativada is not None and desativada.is_active is False

    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("15.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )

    assert resultado.needs_category is True
    assert resultado.transaction.category_id is None


@pytest.mark.asyncio
async def test_excluir_marca_deleted_at_e_nao_remove_a_linha() -> None:
    service, _ = _novo_service()
    user_id = uuid.uuid4()
    resultado = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("30.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )

    excluida = await service.delete_transaction(user_id, resultado.transaction.id)

    assert excluida is True
    assert resultado.transaction.deleted_at is not None


@pytest.mark.asyncio
async def test_segunda_chamada_com_mesma_idempotency_key_devolve_resultado_original() -> None:
    service, _ = _novo_service()
    user_id = uuid.uuid4()

    primeira = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("45.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
        description="Mercado",
        idempotency_key="msg-123",
    )

    segunda = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("999.00"),  # parâmetros diferentes — não deveriam importar num replay
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
        description="Outra coisa",
        idempotency_key="msg-123",
    )

    assert segunda.transaction.id == primeira.transaction.id
    assert segunda.transaction.amount == Decimal("45.00")
    assert segunda.transaction.description == "Mercado"


@pytest.mark.asyncio
async def test_idempotency_keys_diferentes_criam_transacoes_diferentes() -> None:
    transaction_repo = InMemoryTransactionRepository()
    service = FinanceService(transaction_repo, InMemoryCategoryRepository())
    user_id = uuid.uuid4()

    primeira = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
        idempotency_key="msg-a",
    )
    segunda = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
        idempotency_key="msg-b",
    )

    assert segunda.transaction.id != primeira.transaction.id
    assert len(await transaction_repo.list_by_user(user_id)) == 2


@pytest.mark.asyncio
async def test_sem_idempotency_key_nao_bloqueia_a_operacao() -> None:
    transaction_repo = InMemoryTransactionRepository()
    service = FinanceService(transaction_repo, InMemoryCategoryRepository())
    user_id = uuid.uuid4()

    primeira = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )
    segunda = await service.create_transaction(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("10.00"),
        currency="BRL",
        source=TransactionSource.CHAT,
        today=_HOJE,
    )

    assert segunda.transaction.id != primeira.transaction.id
    assert len(await transaction_repo.list_by_user(user_id)) == 2
