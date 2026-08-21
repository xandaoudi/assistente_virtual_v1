import asyncio


def loop_factory() -> asyncio.AbstractEventLoop:
    """SelectorEventLoop em qualquer plataforma.

    Uvicorn escolhe ProactorEventLoop por padrão no Windows, mas o psycopg
    assíncrono não roda sobre ele. SelectorEventLoop já é o padrão no Linux,
    então usar este factory em todo lugar (dev e produção) elimina a
    distinção — em vez de um `--loop` condicional por plataforma.

    Assinatura sem argumentos de propósito: para uma string de `--loop`
    customizada (fora de none/auto/asyncio/uvloop), o uvicorn importa e
    chama a função diretamente esperando a instância do loop de volta —
    diferente do protocolo `(use_subprocess) -> Callable[[], loop]` usado
    pelos factories embutidos dele.
    """
    return asyncio.SelectorEventLoop()
