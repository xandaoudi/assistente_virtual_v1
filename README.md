# assistente_virtual_v1

Assistente virtual de finanças pessoais. Ver `requirements.md` para o escopo completo.

## Pré-requisitos

| Ferramenta | Versão | Observação |
|---|---|---|
| Python | 3.12 | o `uv` baixa e gerencia essa versão sozinho — não precisa instalar à parte |
| [uv](https://docs.astral.sh/uv/) | 0.8+ | gerenciador de dependências e ambiente virtual do projeto |
| Git | qualquer recente | |
| Docker Desktop | rodando | usa WSL2 por baixo, mas os comandos abaixo são todos PowerShell |

Os comandos deste README são **PowerShell**, porque é onde você vai rodá-los no dia a dia (`cp`, `export` etc. do bash não existem aqui).

## Clonar e instalar

```powershell
git clone <url-do-repositorio>
cd assistente_virtual_v1
uv sync --frozen
```

`--frozen` instala exatamente as versões travadas em `uv.lock`, sem tentar resolver de novo. Se o comando reclamar que o lock está desatualizado, alguém esqueceu de rodar `uv lock` antes de commitar — não rode `uv lock` você mesmo para "resolver", investigue o `pyproject.toml`.

## Configurar o `.env`

```powershell
Copy-Item .env.example .env
```

O `.env.example` já vem apontando para o Postgres de desenvolvimento deste README (porta `5433` — veja a nota abaixo). Não precisa editar nada para rodar localmente.

## Subir o banco de desenvolvimento

```powershell
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml exec db pg_isready
```

Deve responder `accepting connections`.

> **Por que a porta é `5433`, não `5432`:** se esta máquina já tiver um Postgres nativo instalado (serviço do Windows, outra instalação local), ele normalmente ocupa a `5432`. O `docker-compose.dev.yml` deste projeto publica em `127.0.0.1:5433` de propósito, para não colidir. Se `5433` também estiver ocupada na sua máquina, mude a porta no `docker-compose.dev.yml` **e** no `DATABASE_URL` do `.env`.

## Aplicar as migrations

```powershell
uv run alembic upgrade head
uv run alembic current
```

O segundo comando deve mostrar a revisão aplicada, marcada como `(head)`.

## Rodar a aplicação

```powershell
uv run uvicorn app.main:app --reload --loop app.core.asyncio_loop:loop_factory
```

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/health/ready
```

Ambos devem responder `200`. Se a porta `8000` já estiver em uso na sua máquina, acrescente `--port <outra-porta>`.

> **Por que o `--loop` customizado:** o `uvicorn` escolhe `ProactorEventLoop` por padrão no Windows, mas a conexão assíncrona do `psycopg` (usada pelo SQLAlchemy) não roda sobre ele — toda chamada ao banco falharia com `psycopg.InterfaceError`. `app/core/asyncio_loop.py` fornece um `SelectorEventLoop`, que funciona em qualquer plataforma; por isso o mesmo comando (com `--loop`) é usado em desenvolvimento e em produção.

## Rodar os testes

```powershell
uv run pytest -m unit          # domínio puro, sem IO
uv run pytest -m integration   # precisa do banco de pé (passo acima)
uv run pytest -m e2e           # sobe a aplicação de verdade
uv run pytest                  # os três níveis juntos
```

## Comandos do dia a dia

| Comando | O que faz |
|---|---|
| `uv run ruff format .` | formata o código |
| `uv run ruff format --check .` | só verifica, não altera (o que o CI roda) |
| `uv run ruff check .` | lint |
| `uv run ruff check --fix .` | lint com correção automática |
| `uv run mypy app` | checagem de tipos estrita |
| `uv run alembic revision -m "mensagem"` | cria uma nova migration vazia |
| `uv run alembic upgrade head` | aplica todas as migrations pendentes |
| `uv run alembic downgrade -1` | desfaz a última migration |
| `docker compose -f docker-compose.dev.yml up -d` | sobe o banco de desenvolvimento |
| `docker compose -f docker-compose.dev.yml stop db` | derruba o banco (sem apagar os dados) |
| `docker compose -f docker-compose.dev.yml down` | derruba o banco e a rede (mantém o volume de dados) |
| `uv add <pacote>` | adiciona dependência de produção (atualiza `pyproject.toml` e `uv.lock`) |
| `uv add --dev <pacote>` | idem, para dependência de desenvolvimento |
| `uv lock` | regera o `uv.lock` depois de editar `pyproject.toml` à mão |

## Portões de qualidade

Todos os comandos acima também rodam no CI (`.github/workflows/ci.yml`) a cada push/PR contra `main`, nessa ordem: instalar dependências travadas, `ruff format`, `ruff check`, `mypy`, testes unitários com cobertura, testes de integração, testes e2e, e checagem de cobertura mínima (80%) em `app/domain` e `app/tools`. A `main` exige esse CI verde para aceitar merge.
