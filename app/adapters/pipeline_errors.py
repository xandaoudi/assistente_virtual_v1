"""Degradação do pipeline do agente (T3.9, RF-71, RNF-16).

Nenhuma mensagem daqui expõe detalhe interno — nem stack trace, nem nome de biblioteca ou
de tabela: `safe_message_for` sempre devolve um texto fixo e pré-escrito, nunca `str(erro)`.

`OperationConfirmedResponseFailedError` é o caso que a Etapa 3 chama de atenção: se uma tool de
escrita (ex.: `create_transaction`) já confirmou a operação no banco antes de o resto do
turno falhar — a resposta em si, por exemplo —, o usuário precisa saber que o lançamento foi
registrado, não receber uma mensagem genérica de erro que sugere tentar de novo.
"""

from pydantic_ai.exceptions import ModelAPIError, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ToolReturnPart

_MENSAGEM_LLM_INDISPONIVEL = (
    "Não consegui falar com o assistente agora. Tente de novo em instantes."
)
_MENSAGEM_TIMEOUT = "Isso demorou mais do que deveria e foi cancelado. Tente de novo."
_MENSAGEM_LIMITE_DE_USO = "Você atingiu o limite de uso no momento. Tente novamente mais tarde."
_MENSAGEM_ERRO_INTERNO = "Ocorreu um erro inesperado. Tente novamente mais tarde."
_MENSAGEM_OPERACAO_CONFIRMADA = (
    "Seu lançamento foi registrado, mas tive um problema para preparar a resposta. "
    "Pode conferir no seu extrato."
)

# Tools de escrita do registro (T2.5, T3.4) — as únicas cuja conclusão bem-sucedida antes de
# uma falha justifica a mensagem de "operação confirmada" em vez do erro genérico.
WRITE_TOOL_NAMES = frozenset(
    {
        "create_transaction",
        "update_transaction",
        "delete_transaction",
        "create_category",
        "update_user_preferences",
    }
)


class OperationConfirmedResponseFailedError(Exception):
    """Uma tool de escrita já confirmou a operação no banco antes de o turno falhar."""


def write_operation_succeeded(messages: list[ModelMessage]) -> bool:
    """`True` quando o histórico capturado do turno contém uma tool de escrita concluída."""
    return any(
        isinstance(part, ToolReturnPart)
        and part.tool_name in WRITE_TOOL_NAMES
        and part.outcome == "success"
        for message in messages
        for part in message.parts
    )


def safe_message_for(erro: Exception) -> str:
    """Traduz qualquer falha do pipeline para uma mensagem segura em português.

    A ordem importa: `OperationConfirmedResponseFailedError` é checado antes de tudo — é o único
    caso em que a operação já aconteceu de verdade. Fora ele, tudo que este módulo não
    reconhece especificamente (inclusive banco indisponível) cai no erro genérico: nunca
    propaga `str(erro)` para quem usa o chat.
    """
    if isinstance(erro, OperationConfirmedResponseFailedError):
        return _MENSAGEM_OPERACAO_CONFIRMADA
    if isinstance(erro, TimeoutError):
        return _MENSAGEM_TIMEOUT
    if isinstance(erro, UsageLimitExceeded):
        return _MENSAGEM_LIMITE_DE_USO
    if isinstance(erro, ModelAPIError):
        return _MENSAGEM_LLM_INDISPONIVEL
    return _MENSAGEM_ERRO_INTERNO
