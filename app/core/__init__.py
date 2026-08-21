import asyncio
import platform

if platform.system() == "Windows":
    # psycopg 3 async não suporta o ProactorEventLoop, padrão do asyncio no
    # Windows desde o Python 3.8. Precisa do SelectorEventLoop.
    #
    # `platform.system()` em vez de `sys.platform` de propósito: o mypy trata
    # `sys.platform == "win32"` como narrowing estático e, rodando em CI Linux,
    # marcaria este bloco como inalcançável — o que reprovaria com
    # `warn_unreachable = true`.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
