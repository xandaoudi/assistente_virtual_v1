from enum import StrEnum


class TransactionType(StrEnum):
    """Tipo de uma transação (e, por extensão, da categoria que ela usa)."""

    EXPENSE = "expense"
    INCOME = "income"


class TransactionSource(StrEnum):
    """Origem de uma transação — de onde o valor veio."""

    CHAT = "chat"
    RECEIPT = "receipt"
    IMPORT = "import"
    RECURRING = "recurring"
