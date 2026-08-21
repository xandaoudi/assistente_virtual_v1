# assistente_virtual_v1 — regras para o Claude Code

Assistente virtual de finanças pessoais. Escopo completo em `requirements.md`.

## Regra arquitetural central (RF-86 / RNF-09)

Dependência **unidirecional**: `adapters → tools → domain → repositório`.

- `app/domain` e `app/tools` **nunca** importam `pydantic_ai` (nem qualquer framework de
  agente). Quem fala com a LLM é `app/adapters`.
- A LLM nunca gera SQL, nunca recebe credenciais de banco, nunca toca o ORM.
- `user_id` é injetado no lado do servidor (via `RunContext`/deps), nunca chega como campo
  do schema visto pela LLM.
- Barreira é reforçada em dois níveis independentes — se um falhar, o outro pega:
  - Ruff: `flake8-tidy-imports` banned-api bloqueia `import pydantic_ai` fora de `adapters/`.
  - Teste: `tests/unit/test_architecture.py` varre `app/domain` e `app/tools` via AST.
- Antes de importar algo novo em `domain`/`tools`, pergunte: isso amarra a lógica de negócio
  a uma tecnologia de IA específica? Se sim, isso é um adapter, não domínio.

## Estrutura de pastas

```
app/domain/        regras de negócio puras, sem IO — inclui os Protocol de repositório
app/models/        modelos ORM (SQLAlchemy) — schema das tabelas, sem regra de negócio
app/repositories/  implementações dos Protocol de app/domain (SQLAlchemy real + em memória p/ testes)
app/tools/         funções Python + schema Pydantic, chamam domain (contrato: seção 5 do requirements.md)
app/adapters/      integrações externas (LLM, MCP, HTTP) — único lugar que pode importar pydantic_ai
app/api/           rotas FastAPI
app/core/          config, db, infraestrutura transversal
alembic/           migrations versionadas do schema do banco
tests/             unit/ integration/ e2e/ (ver marcadores abaixo)
tasks/             docs de planejamento por etapa (gitignored, não entra no repo)
```

## Convenções de código

- Python 3.12, type hints obrigatórios em toda função/método. `mypy --strict` sobre o projeto.
- Sem lógica de negócio fora de `domain`; `tools` só valida, injeta `user_id` e delega.
- Docstring só onde tem leitor: serviços públicos de `domain` e `tools`. Docstring de tool é
  enviada à LLM em toda requisição — curta e precisa, é código de produção pago por token.
- Config sempre via `app.core.config.get_settings()` (Pydantic Settings). Nunca ler
  `os.environ` direto, nem hardcodar `DATABASE_URL` em `alembic.ini`.
- `/health` nunca toca o banco (liveness pura). `/health/ready` é quem faz `SELECT 1`.

## Testes

**Regra de ouro: TDD.** Escreva o teste primeiro, depois a funcionalidade que o faz passar.
Se um teste quebrar, o padrão é corrigir a funcionalidade — nunca o teste — a menos que o
teste em si esteja comprovadamente errado (e isso é a exceção, não a resposta padrão).

Três marcadores (`-m unit|integration|e2e`), sem overlap:

- `unit`: domínio puro, sem IO.
- `integration`: precisa do Postgres de dev de pé (`docker-compose.dev.yml`).
- `e2e`: sobe a aplicação de verdade (subprocess uvicorn).

Nenhum teste, em nenhuma hipótese, chama a LLM de verdade — `tests/conftest.py` trava isso
via `pydantic_ai.models.ALLOW_MODEL_REQUESTS = False`. Cobertura mínima de 80% em
`app/domain` e `app/tools`, sem LLM no circuito (RNF-19).

## Antes de commitar

`uv run ruff format --check .` · `uv run ruff check .` · `uv run mypy app` · `uv run pytest`
— é exatamente o que o CI roda; se algo falhar aqui, falha lá.

## Coisas que já morderam este projeto (não repetir)

- Windows usa `ProactorEventLoop` por padrão no uvicorn, incompatível com psycopg async.
  Sempre rodar com `--loop app.core.asyncio_loop:loop_factory` (dev e prod, mesmo comando).
- `uv sync --frozen` **não** valida se o lock está consistente com o `pyproject.toml`; use
  `--locked` quando a intenção é validar (é o que o CI faz).
- Engine/sessionmaker do banco (`app/core/db.py`) são `lru_cache` lazy — nunca eager no
  import do módulo, senão `/health` (liveness) passa a exigir `DATABASE_URL` sem precisar.
