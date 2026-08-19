# Requisitos — Assistente Virtual Pessoal (Agenda + Finanças)

**Projeto:** `assistente_virtual_v1`
**Autor:** Alexandre
**Versão do documento:** 1.0 — **baseline aprovada para início do desenvolvimento**
**Data:** 19/08/2026

**Decisões travadas nesta versão:**

| Decisão | Escolha |
|---|---|
| Framework de agente | **Pydantic AI** (pacote enxuto `pydantic-ai-slim`) |
| Provedor de LLM (fase 1) | **Google Gemini**, atrás da abstração do RNF-08 |
| Mecanismo de tools (Q-01) | **Opção C** — function calling nativo em produção, caminho MCP preparado |
| Escopo da Fase 1 | OCR de recibo **adiado** para a Fase 1.5; sync com Google Calendar **mantido** |
| Histórico de conversa (Q-07) | **Tabela própria**, não a memória do framework |

**Mudanças desde a v0.2:** §3.3 fechada com decisão; stack atualizada de Agno para Pydantic AI; RF-36/RF-37 movidos para a Fase 1.5; nova §13 com ordem de implementação.

---

## 1. Visão Geral

Um assistente virtual pessoal, conversacional, que ajuda o usuário a gerenciar dois domínios do dia a dia:

1. **Agenda** — criar, consultar, remarcar e cancelar compromissos e eventos.
2. **Finanças** — registrar despesas e receitas, e consultar gastos por período, por categoria, saldo, comparativos e tendências.

A interação acontece por **linguagem natural**. O usuário escreve algo como *"marca dentista quinta às 15h"* ou *"quanto gastei com mercado esse mês?"* e o assistente entende, executa a ação e responde em texto natural.

### 1.1 Princípio arquitetural central

> **A LLM nunca toca no banco de dados.**

A LLM atua exclusivamente como **camada de interpretação e orquestração**. Ela:

- interpreta a intenção do usuário;
- decide **qual ferramenta (tool)** chamar e com **quais parâmetros**;
- recebe o resultado estruturado da ferramenta;
- redige a resposta em linguagem natural.

Toda leitura e escrita de dados passa por uma **camada de serviços (tools)** determinística, validada e testável. A LLM não gera SQL, não recebe credenciais de banco e não tem acesso ao ORM. Isso garante:

- **Segurança** — nenhum risco de SQL injection via prompt ou de vazamento entre usuários.
- **Auditabilidade** — toda mutação passa por um ponto de controle logado.
- **Testabilidade** — a lógica de negócio é testada sem LLM no circuito.
- **Portabilidade de modelo** — trocar a LLM (nuvem → local) não altera a lógica de negócio.

### 1.2 Objetivos do produto

| # | Objetivo |
|---|---|
| OBJ-01 | Reduzir o atrito de registrar gastos a uma única mensagem de texto ou foto. |
| OBJ-02 | Permitir consultar a agenda e as finanças conversando, sem navegar por telas. |
| OBJ-03 | Dar visibilidade financeira sem exigir disciplina de planilha. |
| OBJ-04 | Evitar esquecimentos por meio de lembretes proativos. |
| OBJ-05 | Ser portável entre canais (Telegram → WhatsApp → Web) sem reescrever o núcleo. |
| OBJ-06 | Ser portável entre LLMs (nuvem → local) sem reescrever o núcleo. |

### 1.3 Não-objetivos (fora de escopo)

- Não é um app de investimentos, corretora ou recomendação financeira.
- Não é um ERP nem ferramenta de contabilidade fiscal.
- Não faz pagamentos, transferências ou qualquer movimentação de dinheiro real.
- Não é uma agenda compartilhada / colaborativa de equipe (v1 é pessoal).

---

## 2. Personas e Casos de Uso

### 2.1 Persona principal

**Usuário pessoal** — adulto, usa Telegram no dia a dia, tem compromissos recorrentes e quer controlar gastos sem manter planilha. Não é necessariamente técnico.

### 2.2 Casos de uso representativos

| ID | Caso de uso | Exemplo de entrada |
|---|---|---|
| UC-01 | Criar compromisso | "marca dentista quinta às 15h" |
| UC-02 | Consultar agenda | "o que eu tenho amanhã?" |
| UC-03 | Remarcar compromisso | "adia a reunião de sexta pra segunda mesma hora" |
| UC-04 | Cancelar compromisso | "cancela o almoço de quarta" |
| UC-05 | Registrar despesa | "gastei 45 no mercado ontem" |
| UC-06 | Registrar despesa por foto *(Fase 1.5)* | *(envia foto do cupom fiscal)* |
| UC-07 | Registrar receita | "recebi 3200 de salário hoje" |
| UC-08 | Consultar gasto por período | "quanto gastei esse mês?" |
| UC-09 | Consultar gasto por categoria | "quanto gastei com transporte em julho?" |
| UC-10 | Comparar períodos | "gastei mais esse mês que no passado?" |
| UC-11 | Ver saldo / resumo | "como estão minhas finanças?" |
| UC-12 | Receber lembrete | *(sistema envia 30 min antes do compromisso)* |
| UC-13 | Receber resumo periódico | *(sistema envia resumo diário da agenda e semanal de gastos)* |
| UC-14 | Corrigir/apagar registro | "aquele gasto de 45 era 54" |

---

## 3. Arquitetura

### 3.1 Visão em camadas

```
┌───────────────────────────────────────────────────────────────┐
│  CANAIS (adapters de entrada/saída)                           │
│  Telegram Bot  │  WhatsApp (fase 2)  │  Web/SPA (fase 3)      │
└──────────────────────────┬────────────────────────────────────┘
                           │  ChannelMessage (formato canônico)
┌──────────────────────────▼────────────────────────────────────┐
│  API / GATEWAY  —  FastAPI                                     │
│  webhooks, autenticação, rate limit, resolução de identidade   │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│  CAMADA DE AGENTE  —  Pydantic AI                              │
│  system prompt · deps (user_id, services) · seleção e          │
│  chamada de tools · redação da resposta                        │
│  (histórico vem da tabela própria, não da memória do framework)│
│         ▲                                                      │
│         │  (só schemas de tools + resultados JSON)             │
└─────────┼──────────────────────────────────────────────────────┘
          │  ❌ SEM acesso a banco
┌─────────▼──────────────────────────────────────────────────────┐
│  CAMADA DE TOOLS  (fronteira de segurança)                     │
│  validação de entrada (Pydantic) · injeção de user_id ·        │
│  autorização · normalização de data/valor · logging            │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│  CAMADA DE DOMÍNIO / SERVIÇOS                                  │
│  CalendarService · FinanceService · CategoryService ·          │
│  ReportService · ReminderService                               │
└──────────────────────────┬─────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────┐
│  PERSISTÊNCIA  —  Repositories / ORM                           │
│  PostgreSQL                                                    │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│  SERVIÇOS TRANSVERSAIS                                          │
│  Scheduler (lembretes/resumos) · LLM Provider (abstração) ·     │
│  Google Calendar Sync · OCR/Visão · Observabilidade             │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 Stack definida

| Camada | Tecnologia | Observação |
|---|---|---|
| Linguagem | **Python 3.12+** | |
| API | **FastAPI** | webhooks dos canais + API REST para o site futuro |
| Orquestração de agente | **Pydantic AI** | `pydantic-ai-slim[google]` — evita arrastar todos os provedores |
| Banco de dados | **PostgreSQL 16+** | relacional + JSONB; `pgvector` opcional para memória semântica |
| ORM / migrations | SQLAlchemy 2.x + Alembic | |
| Validação | Pydantic v2 | schemas de tools e DTOs |
| Scheduler | APScheduler (MVP) → Celery/Redis (escala) | ver RNF-14 |
| LLM (fase 1) | **Google Gemini** | via abstração de provider (RNF-08); tier gratuito para desenvolvimento |
| LLM (fase futura) | Modelo local via Ollama / vLLM | requisito RNF-08 |
| Canal (fase 1) | Telegram Bot API (webhook) | |

> **Nota sobre Pydantic AI:** foi escolhido por um motivo direto — sua **injeção de dependências** (`deps_type` + `RunContext`) resolve nativamente o requisito mais crítico do sistema: o `user_id` chega às tools sem jamais entrar no schema visto pela LLM (RNF-04, CA-13). Some-se a isso a mesma família do Pydantic v2 e do FastAPI já adotados, troca de modelo por configuração (RNF-08) e observabilidade OpenTelemetry nativa (RNF-18, RNF-22).
>
> **O que NÃO usaremos do framework:** a camada de memória do *Harness* está em versões 0.x, com API sujeita a mudança entre releases menores. Como o RF-65 (contexto de conversa) é Must, o histórico fica em **tabela própria** (`conversations`/`messages`, seção 6). Decisão da Q-07.
>
> Mesmo assim, o desenho mantém a **fronteira de tools** independente do framework — os serviços de domínio não importam nada de Pydantic AI (ver RNF-09 e §3.3.7).

### 3.3 Mecanismo de chamada de tools — **DECIDIDO: Opção C**

> **Decisão (v1.0):** function calling nativo via Pydantic AI em produção, com o código organizado de modo que expor as mesmas tools via MCP seja escrever um adapter, não refatorar o sistema. O adapter MCP **não será construído** até que um dos gatilhos da §3.3.6 ocorra.
>
> As subseções abaixo preservam a análise que levou a essa decisão — servem de justificativa registrada e de base para revisá-la no futuro.

O **contrato das tools** (nome, parâmetros, tipos, retorno, erros) está definido na seção 5 e é **obrigatório**. O que fica em aberto é o **mecanismo de transporte**: como o schema chega até a LLM e como a chamada volta até o código.

#### 3.3.1 O que está em jogo — e o que não está

Vale separar o que essa decisão afeta do que ela não afeta, porque a confusão entre as duas coisas é a fonte usual de over-engineering aqui.

**Não muda com a escolha:**

- O catálogo de tools e suas assinaturas (seção 5).
- A lógica de domínio (`CalendarService`, `FinanceService` etc.).
- A quantidade de tokens de schema enviados à LLM (§3.3.5).
- A qualidade da decisão do modelo sobre qual tool chamar.
- O fato de a LLM não tocar no banco (§1.1) — isso já está garantido pela existência da camada de tools, seja qual for o transporte.

**Muda com a escolha:**

- Como o `user_id` é injetado, e quão fácil é errar isso (§3.3.3).
- Latência por chamada de tool.
- Número de processos a operar, versionar e monitorar.
- Se as tools podem ser consumidas por clientes externos (Claude Desktop, IDEs, outros agentes).
- Onde mora a fronteira de falha quando algo quebra às 3h da manhã.

#### 3.3.2 As opções

**Opção A — Function calling nativo, tools no processo do agente**

As tools são funções Python decoradas, registradas no `Agent` do Pydantic AI. O framework serializa os schemas, envia ao modelo, recebe a intenção de chamada e executa a função no mesmo processo.

```
[FastAPI] → [Pydantic AI Agent] → chamada de função em memória → [Service] → [Postgres]
```

**Opção B — Servidor MCP separado**

As tools vivem num processo próprio que fala o Model Context Protocol. O agente é um cliente MCP. Tanto o Pydantic AI quanto o Agno suportam isso, com transportes stdio, SSE ou Streamable HTTP.

```
[FastAPI] → [Agent] --MCP/HTTP--> [Servidor MCP] → [Service] → [Postgres]
```

**Opção C — Híbrido**

Serviços de domínio no núcleo, com **dois adapters finos**: um que registra as tools no Pydantic AI (usado em produção) e outro que as expõe como servidor MCP (usado para depuração, uso pessoal via Claude Desktop, e como caminho de migração).

Uma variante mais defensável da C: expor via MCP **apenas as tools de leitura** (`get_summary`, `list_events`, `get_spending_by_category`…) e manter as de escrita exclusivamente in-process. Reduz drasticamente a superfície de risco mantendo o benefício de inspecionar os dados de fora.

#### 3.3.3 A dimensão crítica: injeção de `user_id`

Esta é a diferença que mais pesa, e ela não é óbvia à primeira vista.

O RNF-04 e o CA-13 exigem que o `user_id` **nunca** venha da LLM. Não basta "a LLM não deveria mandar" — o requisito é que ela **não consiga**.

**Com a Opção A**, isso sai de graça, por construção:

```python
@dataclass
class Deps:
    user_id: UUID                 # resolvido pelo gateway, invisível para a LLM
    finance: FinanceService

@agent.tool
async def get_summary(ctx: RunContext[Deps], start_date: date,
                      end_date: date) -> SummaryResult:
    # ctx NÃO entra no schema — a LLM só vê start_date e end_date
    return await ctx.deps.finance.get_summary(ctx.deps.user_id,
                                              start_date, end_date)
```

A LLM literalmente não tem onde escrever um `user_id`. O campo não existe no schema. O CA-13 é satisfeito por **impossibilidade estrutural**, não por validação — e, no Pydantic AI, essa separação é imposta pela assinatura da função com verificação de tipos, não por convenção do projeto.

**Com a Opção B**, o servidor MCP é outro processo e precisa descobrir de quem é a requisição. Os caminhos possíveis:

| Abordagem | Problema |
|---|---|
| Uma sessão MCP por usuário | Conexão por usuário. A documentação dos frameworks avisa que gerenciar conexão por execução tem impacto de performance e não é recomendado em produção. |
| Token de escopo passado em header HTTP | Funciona, e a spec de 2026-07-28 até facilita com roteamento por header. Mas exige que o adapter injete e o servidor valide corretamente **em toda chamada**. |
| `user_id` como parâmetro da tool | **Inaceitável.** Viola RNF-04 e CA-13 diretamente. |

A opção do meio é a correta, mas repare no que aconteceu: o CA-13 deixou de ser garantido *por construção* e passou a ser garantido *se o adapter estiver certo*. Para um sistema multiusuário que guarda dados financeiros, essa é uma degradação real do argumento de segurança — troca-se uma propriedade estrutural por uma propriedade que depende de code review e de teste.

Some-se a isso que a documentação de MCP dos frameworks avaliados **não cobre** isolamento multi-tenant nem credenciais por usuário. Fazer isso corretamente significa estender o framework além do que está documentado — em cima do requisito mais sensível do sistema. É precisamente o oposto do que a injeção de dependências do Pydantic AI oferece no caminho in-process, onde o isolamento é o comportamento padrão e documentado.

> **Conclusão desta subseção:** a Opção B não é inviável, mas ela move o requisito de isolamento entre usuários de "impossível de violar" para "possível de violar se alguém errar o adapter". Num app de finanças pessoais, esse é um preço alto por um benefício que (§3.3.4) é em boa parte hipotético no MVP.

#### 3.3.4 Comparação dimensão a dimensão

| Dimensão | A — Nativo | B — MCP separado | C — Híbrido |
|---|---|---|---|
| **Garantia do RNF-04/CA-13** | Por construção — `user_id` não existe no schema | Depende do adapter estar correto | Por construção no caminho de escrita |
| **Latência por chamada** | Chamada de função (µs) | +1 a 5 ms por chamada (loopback); mais se em rede | Igual à A em produção |
| **Processos a operar** | 1 (+ scheduler) | 2 (+ scheduler) | 1 em produção, 2 sob demanda |
| **Modos de falha novos** | Nenhum | Servidor MCP fora do ar, timeout, reconexão, versão do protocolo | Confinados ao caminho opcional |
| **Testabilidade das tools** | Alta — são funções Python, `pytest` direto | Alta — mas testar o transporte exige subir o servidor | Alta |
| **Depuração** | Stack trace único | Correlacionar dois processos | Único em produção |
| **Reuso por outros clientes** | Não | **Sim** — Claude Desktop, IDEs, outros agentes | Sim, opcionalmente |
| **Portabilidade entre LLMs** | Igual — quem abstrai é o RNF-08, não o transporte | Igual | Igual |
| **Tempo até o MVP** | Menor | +1 a 2 semanas (transporte, auth, deploy, observabilidade) | Igual à A, se o adapter MCP ficar para depois |
| **Risco de churn de spec** | Nenhum | Real: a spec de 2026-07-28 tornou o protocolo stateless, removeu o handshake `initialize` e depreciou o transporte HTTP+SSE com janela de 12 meses | Contido |
| **Consumo de memória** | ~600 MB | ~900 MB (processo extra) | ~600 MB |
| **Superfície de ataque** | Menor | Maior — um endpoint a mais falando com o domínio | Menor em produção |

**Sobre o "reuso por outros clientes":** é o argumento mais forte a favor do MCP, e merece ser examinado com honestidade. Quem seriam esses clientes?

- *Você, depurando pelo Claude Desktop.* Benefício real, mas resolvido por uma variante somente-leitura (§3.3.2) ou por um endpoint HTTP interno protegido.
- *Outros agentes de terceiros.* Não é objetivo do produto (§1.3), e permitir que um cliente MCP genérico alcance dados financeiros de usuários é um risco, não uma funcionalidade.
- *O frontend web da Fase 3.* Vai consumir a API REST do FastAPI, não MCP. MCP é um protocolo agente↔ferramenta, não frontend↔backend.

Ou seja: o benefício principal do MCP neste projeto é **ferramental de desenvolvimento**, não capacidade de produto. Isso não o desqualifica — só reposiciona o quanto ele deveria pesar na decisão.

#### 3.3.5 Custo de tokens dos schemas — o eixo que a discussão costuma ignorar

Independentemente da opção escolhida, **os schemas das tools vão em toda requisição à LLM**. Com as 24 tools do catálogo da seção 5:

| Tokens por schema | Total por requisição |
|---|---|
| 90 (schemas enxutos) | ~2.160 |
| 130 (realista) | ~3.120 |
| 180 (descrições longas) | ~4.320 |

Projetando o custo apenas do schema, assumindo 100 mensagens/dia e ~2 chamadas de LLM por mensagem (uma para decidir a tool, outra para redigir a resposta):

| Modelo | Tokens/mês só de schema | Custo/mês só de schema |
|---|---|---|
| GPT-4o mini | ~18,7 M | ~US$ 2,80 |
| GPT-4o | ~18,7 M | ~US$ 47 |
| Claude Sonnet | ~18,7 M | ~US$ 56 |

> Estimativas de ordem de grandeza, com preços de entrada vigentes e sem cache de prompt. Precisam ser medidas na prática (RNF-18) — mas a conclusão qualitativa é robusta: **com um modelo grande, o schema das tools pode custar mais que as conversas.**

Três consequências de projeto, todas independentes de A/B/C:

1. **Descrições de tools são código de produção, não documentação.** Cada palavra é paga em toda requisição. O RNF-11 (prompts em arquivos versionados) existe também por isso.
2. **Vale considerar carregamento seletivo de tools.** Numa mensagem claramente financeira, as 7 tools de agenda não precisam ir. Reduz custo e melhora a acurácia da escolha — menos opções, menos confusão. Isso vira uma nova questão em aberto (Q-09).
3. **Cache de prompt muda a conta.** Se o provedor suportar, os schemas ficam no prefixo estável e o custo cai bastante. Critério a incluir na avaliação da Q-02.

Aqui, curiosamente, o MCP tem um ponto a favor que raramente é citado: a spec de 2026-07-28 adicionou `ttlMs` e `cacheScope` nas listagens de tools, pensando exatamente nesse problema. É um argumento pró-B mais concreto do que o "desacoplamento" genérico.

#### 3.3.6 Decisão

**Opção C, começando pela A.** Em produção, function calling nativo via Pydantic AI; o adapter MCP fica como caminho preparado, não construído.

O raciocínio:

- O ganho decisivo da A é o `user_id` ser inviolável por construção (§3.3.3), no requisito mais sensível do sistema.
- O ganho principal da B é ferramental de desenvolvimento, não capacidade de produto (§3.3.4).
- O RF-86 já obriga o desacoplamento que torna a migração barata. Adiar a construção do adapter MCP não custa retrabalho — custa apenas não ter o adapter ainda.
- A spec do MCP passou por mudança estruturante em julho de 2026 (protocolo stateless, transporte SSE depreciado com 12 meses de janela). Adotá-la no núcleo agora significa acompanhar essa migração enquanto se constrói o MVP.
- Com o Pydantic AI, o ganho da Opção A fica ainda maior: a injeção de dependências torna o isolamento entre usuários um recurso do framework, não uma convenção a ser mantida por disciplina.

**Gatilhos que justificariam migrar para B:**

| Gatilho | Por quê |
|---|---|
| Surgir um segundo consumidor real das tools | O desacoplamento deixa de ser hipotético |
| As tools precisarem escalar separadamente do agente | Separação de processos passa a ter valor operacional |
| O ecossistema MCP entregar auth multi-tenant madura | O problema do §3.3.3 deixa de existir |
| Abrir a plataforma para integrações de terceiros | Deixa de ser não-objetivo (§1.3) |

Nenhum desses gatilhos está presente hoje. Se algum aparecer, o RF-86 garante que a mudança é escrever um adapter, não reescrever o sistema.

#### 3.3.7 O que exatamente o RF-86 obriga

Para a recomendação acima ser verdadeira, o desacoplamento precisa ser real, não uma intenção. Concretamente:

```
app/
  domain/               # regras de negócio puras
    calendar_service.py #   NÃO importa pydantic_ai, FastAPI nem MCP
    finance_service.py
  tools/
    schemas.py          # modelos Pydantic de entrada e saída de cada tool
    registry.py         # funções puras: (user_id, params) -> resultado tipado
  adapters/
    agent_tools.py      # registra o registry no Agent (Pydantic AI)
    mcp_server.py       # (futuro) expõe o MESMO registry via MCP
    http_tools.py       # (futuro) expõe o MESMO registry via REST
```

O teste de que o desacoplamento é real: **`grep -rl "pydantic_ai" app/domain app/tools` deve retornar vazio.** Se retornar qualquer coisa, o RF-86 foi violado e a Opção C deixou de estar disponível sem retrabalho.

Isso deve rodar **automaticamente em CI**, não como boa intenção:

```bash
# falha o build se o domínio ou as tools importarem o framework de agente
! grep -rl "pydantic_ai" app/domain app/tools
```

**Requisito derivado:** as tools devem ser funções Python puras com schema Pydantic, de modo que expor via Pydantic AI, via MCP ou via HTTP seja apenas um adapter — sem reescrever lógica. (Ver RF-86 e RNF-09.)

### 3.4 Fluxo de uma mensagem

1. Canal recebe a mensagem → converte para `ChannelMessage` canônico (`{channel, external_user_id, text|media, timestamp}`).
2. Gateway resolve a **identidade** (`external_user_id` → `user_id` interno). Se não existir, dispara onboarding.
3. Agente carrega contexto: system prompt + preferências do usuário (timezone, moeda) + histórico recente da sessão.
4. LLM decide: responder direto **ou** chamar uma ou mais tools.
5. Camada de tools valida os parâmetros, **injeta o `user_id` do lado do servidor** (nunca vindo da LLM — ver RNF-04) e chama o serviço de domínio.
6. Serviço executa, persiste, retorna resultado estruturado.
7. LLM redige a resposta final em português natural.
8. Canal formata e envia.

---

## 4. Requisitos Funcionais

### 4.1 Identidade e Conta

| ID | Requisito | Prioridade |
|---|---|---|
| RF-01 | O sistema deve ser **multiusuário**, com isolamento total de dados entre usuários. | Must |
| RF-02 | O sistema deve identificar o usuário pelo identificador externo do canal (ex.: `chat_id` do Telegram) e mapeá-lo para um `user_id` interno. | Must |
| RF-03 | Um mesmo usuário deve poder vincular **múltiplos canais** (Telegram, WhatsApp, Web) à mesma conta, via código de vinculação. | Should |
| RF-04 | No primeiro contato, o sistema deve executar um onboarding curto capturando: nome, fuso horário e moeda padrão. | Must |
| RF-05 | O usuário deve poder solicitar a exportação de todos os seus dados (JSON/CSV). | Should |
| RF-06 | O usuário deve poder solicitar a exclusão da conta e de todos os seus dados. | Must |

### 4.2 Agenda

| ID | Requisito | Prioridade |
|---|---|---|
| RF-10 | Criar evento a partir de linguagem natural, extraindo título, data, hora de início, duração e local (quando presente). | Must |
| RF-11 | Assumir **duração padrão de 1 hora** quando não informada, e informar essa suposição na resposta. | Must |
| RF-12 | Interpretar datas relativas ("amanhã", "quinta que vem", "daqui a 15 dias") sempre no **fuso horário do usuário**. | Must |
| RF-13 | Pedir confirmação ao usuário quando data ou hora forem **ambíguas** (ex.: "sexta" sem hora, "às 3" sem AM/PM). | Must |
| RF-14 | Listar eventos por intervalo de datas (hoje, amanhã, esta semana, intervalo arbitrário). | Must |
| RF-15 | Buscar eventos por texto no título/descrição. | Should |
| RF-16 | Atualizar um evento existente (data, hora, título, duração, local). | Must |
| RF-17 | Cancelar/excluir um evento, sempre com **confirmação explícita** do usuário antes de efetivar. | Must |
| RF-18 | Detectar **conflito de horário** ao criar ou remarcar e alertar o usuário, sem bloquear a operação. | Should |
| RF-19 | Suportar eventos recorrentes (diário, semanal, mensal, anual) e a edição de "só esta ocorrência" vs. "toda a série". | Could |
| RF-20 | Sincronizar eventos bidirecionalmente com o **Google Calendar** via OAuth 2.0. | Must (MVP) |
| RF-21 | Na sincronização, tratar conflitos pela regra **last-write-wins** com registro em log; eventos criados fora do assistente devem aparecer nas consultas. | Must |
| RF-22 | Permitir ao usuário desconectar o Google Calendar a qualquer momento, mantendo os eventos locais. | Should |

### 4.3 Finanças — Registro

| ID | Requisito | Prioridade |
|---|---|---|
| RF-30 | Registrar **despesa** a partir de linguagem natural, extraindo valor, descrição, data e categoria. | Must |
| RF-31 | Registrar **receita** a partir de linguagem natural, com os mesmos campos. | Must |
| RF-32 | Assumir a **data de hoje** quando não informada. | Must |
| RF-33 | Interpretar valores em formato brasileiro ("45", "45,90", "R$ 1.250,00", "1,2k"). | Must |
| RF-34 | Sugerir automaticamente a **categoria** a partir da descrição, permitindo que o usuário corrija. | Must |
| RF-35 | Solicitar confirmação antes de gravar quando a confiança na extração for baixa (valor ou data incertos). | Must |
| RF-36 | Registrar despesa a partir de **foto de recibo/nota fiscal** (OCR + extração multimodal), apresentando os dados extraídos para confirmação do usuário **antes** de gravar. | **Fase 1.5** |
| RF-37 | Anexar a imagem original à transação criada por foto, para consulta posterior. | **Fase 1.5** |
| RF-38 | Editar uma transação já registrada (valor, data, categoria, descrição). | Must |
| RF-39 | Excluir uma transação, com confirmação explícita. | Must |
| RF-40 | Suportar múltiplos **métodos de pagamento** (dinheiro, débito, crédito, PIX) como atributo da transação. | Should |
| RF-41 | Suportar transações **recorrentes** (assinaturas, salário, aluguel) com geração automática. | Could |
| RF-42 | Suportar despesa **parcelada**, registrando as parcelas futuras. | Could |

### 4.4 Finanças — Categorias

| ID | Requisito | Prioridade |
|---|---|---|
| RF-45 | Fornecer um conjunto padrão de categorias na criação da conta (Alimentação, Mercado, Transporte, Moradia, Saúde, Educação, Lazer, Vestuário, Assinaturas, Outros). | Must |
| RF-46 | Permitir criar, renomear e desativar categorias personalizadas. | Should |
| RF-47 | Categorias devem ser por usuário; desativar uma categoria não deve apagar as transações históricas associadas. | Must |
| RF-48 | Suportar categorias distintas para receita e despesa. | Should |

### 4.5 Finanças — Consultas e Relatórios

| ID | Requisito | Prioridade |
|---|---|---|
| RF-50 | Total de despesas por período (dia, semana, mês, ano, intervalo arbitrário). | Must |
| RF-51 | Total de receitas por período. | Must |
| RF-52 | **Saldo** do período (receitas − despesas). | Must |
| RF-53 | Gastos **agrupados por categoria** em um período, com valor absoluto e percentual do total. | Must |
| RF-54 | Gastos de **uma categoria específica** em um período. | Must |
| RF-55 | **Comparação entre dois períodos** (ex.: mês atual vs. mês anterior), com variação absoluta e percentual. | Should |
| RF-56 | Listagem das transações de um período, com filtros por categoria, faixa de valor e texto. | Must |
| RF-57 | Ranking das maiores despesas de um período (top N). | Should |
| RF-58 | Evolução mensal dos gastos ao longo de N meses (série temporal). | Should |
| RF-59 | Interpretar períodos em linguagem natural ("esse mês", "últimos 30 dias", "em julho", "no ano passado"). | Must |
| RF-60 | Definir **orçamento (budget)** mensal por categoria e alertar ao ultrapassar um limiar configurável (ex.: 80% e 100%). | Could |
| RF-61 | Exportar relatório do período em CSV. | Could |

### 4.6 Conversação e Comportamento do Agente

| ID | Requisito | Prioridade |
|---|---|---|
| RF-65 | O agente deve manter **contexto da conversa** para permitir follow-ups ("e no mês passado?", "muda pra 16h"). | Must |
| RF-66 | O agente deve pedir esclarecimento em vez de adivinhar quando faltar informação essencial (valor, data de compromisso). | Must |
| RF-67 | O agente deve exigir **confirmação explícita** antes de qualquer operação destrutiva (excluir evento, excluir transação, excluir conta). | Must |
| RF-68 | O agente deve responder em **português do Brasil**, em tom natural e conciso, formatando valores em BRL e datas no padrão brasileiro. | Must |
| RF-69 | O agente deve conseguir executar **múltiplas ações em uma mensagem** ("marca o dentista quinta e registra os 45 do mercado"). | Should |
| RF-70 | O agente deve recusar, com resposta educada, pedidos fora do escopo de agenda e finanças, redirecionando ao que ele faz. | Must |
| RF-71 | O agente deve informar quando uma tool falhar, sem expor stack trace, ID interno ou detalhe de infraestrutura. | Must |
| RF-72 | O agente deve permitir ao usuário desfazer a última ação de escrita ("desfaz isso") dentro de uma janela curta. | Could |

### 4.7 Proatividade (Lembretes e Resumos)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-75 | Enviar lembrete de compromisso com antecedência configurável (padrão: 30 minutos). | Must |
| RF-76 | Permitir ao usuário definir uma antecedência específica por evento ("me lembra 2h antes"). | Should |
| RF-77 | Enviar **resumo diário** da agenda em horário configurável (padrão: 07h00 no fuso do usuário). | Must |
| RF-78 | Enviar **resumo semanal** de finanças (total gasto, top categorias, comparação com a semana anterior). | Must |
| RF-79 | Permitir ao usuário ativar/desativar cada tipo de notificação individualmente. | Must |
| RF-80 | Garantir que uma notificação **não seja enviada duas vezes** (idempotência do scheduler). | Must |
| RF-81 | Não enviar notificações fora da janela de horário permitida pelo usuário (quiet hours). | Should |

### 4.8 Camada de Tools

| ID | Requisito | Prioridade |
|---|---|---|
| RF-85 | Toda operação de dados deve ser exposta à LLM exclusivamente como tool com schema tipado (nome, descrição, parâmetros, retorno). | Must |
| RF-86 | As tools devem ser implementadas como funções puras sobre os serviços de domínio, **sem dependência do framework de agente**, permitindo expor via function calling, MCP ou HTTP com adapters finos. | Must |
| RF-87 | Toda tool deve retornar um resultado estruturado com indicação de sucesso/erro e mensagem legível, nunca uma exceção crua. | Must |
| RF-88 | Toda chamada de tool deve ser registrada em log de auditoria (usuário, tool, parâmetros, resultado, duração, timestamp). | Must |
| RF-89 | Tools de escrita devem ser **idempotentes** quando possível, via chave de idempotência derivada da requisição. | Should |

---

## 5. Catálogo de Tools

Contrato obrigatório. `user_id` **nunca** é parâmetro da LLM — é injetado pelo servidor a partir da sessão autenticada (RNF-04). Todas as datas em ISO 8601, no fuso do usuário.

### 5.1 Agenda

| Tool | Parâmetros | Retorno |
|---|---|---|
| `create_event` | `title`, `start_datetime`, `duration_minutes?`, `location?`, `description?`, `reminder_minutes_before?`, `recurrence?` | `event_id`, dados do evento, `conflicts[]` |
| `list_events` | `start_date`, `end_date`, `limit?` | lista de eventos |
| `get_event` | `event_id` | evento |
| `search_events` | `query`, `start_date?`, `end_date?` | lista de eventos |
| `update_event` | `event_id`, campos alteráveis, `scope?` (`this`\|`series`) | evento atualizado, `conflicts[]` |
| `delete_event` | `event_id`, `scope?` | confirmação |
| `check_availability` | `start_datetime`, `duration_minutes` | `available: bool`, `conflicts[]` |

### 5.2 Finanças — escrita

| Tool | Parâmetros | Retorno |
|---|---|---|
| `create_transaction` | `type` (`expense`\|`income`), `amount`, `description`, `date?`, `category?`, `payment_method?`, `attachment_id?` | `transaction_id`, transação normalizada, `category_confidence` |
| `update_transaction` | `transaction_id`, campos alteráveis | transação atualizada |
| `delete_transaction` | `transaction_id` | confirmação |
| `parse_receipt` *(Fase 1.5)* | `attachment_id` | campos extraídos + `confidence` (**não persiste** — RF-36) |

### 5.3 Finanças — consulta

| Tool | Parâmetros | Retorno |
|---|---|---|
| `get_summary` | `start_date`, `end_date` | total receitas, total despesas, saldo, nº de transações |
| `get_spending_by_category` | `start_date`, `end_date`, `type?` | lista `{categoria, total, percentual, contagem}` |
| `get_category_spending` | `category`, `start_date`, `end_date` | total, contagem, média |
| `list_transactions` | `start_date`, `end_date`, `category?`, `type?`, `min_amount?`, `max_amount?`, `query?`, `limit?` | lista de transações |
| `compare_periods` | `period_a_start/end`, `period_b_start/end`, `group_by?` | totais dos dois períodos + variação abs. e % |
| `get_top_expenses` | `start_date`, `end_date`, `limit` | maiores despesas |
| `get_monthly_trend` | `months` | série temporal mensal |

### 5.4 Categorias, preferências e utilidades

| Tool | Parâmetros | Retorno |
|---|---|---|
| `list_categories` | `type?` | categorias do usuário |
| `create_category` | `name`, `type` | categoria criada |
| `get_user_preferences` | — | timezone, moeda, notificações |
| `update_user_preferences` | campos alteráveis | preferências atualizadas |
| `set_reminder` | `event_id`, `minutes_before` | confirmação |
| `resolve_relative_date` | `expression`, `reference_date?` | data absoluta resolvida |

> `resolve_relative_date` existe para tirar a aritmética de datas da LLM — fonte comum de erro — e devolvê-la a código determinístico.

---

## 6. Modelo de Dados (visão lógica)

```
users
  id (uuid, pk) · name · timezone · currency · locale
  created_at · updated_at · deleted_at

user_channels                       -- vínculo canal ↔ conta (RF-03)
  id · user_id (fk) · channel (telegram|whatsapp|web)
  external_id · is_primary · linked_at
  UNIQUE (channel, external_id)

user_preferences
  user_id (fk, pk)
  daily_summary_enabled · daily_summary_time
  weekly_report_enabled · weekly_report_weekday
  default_reminder_minutes · quiet_hours_start · quiet_hours_end

events
  id · user_id (fk) · title · description · location
  start_datetime (timestamptz) · end_datetime (timestamptz)
  status (scheduled|cancelled|done)
  recurrence_rule (RRULE, nullable) · parent_event_id (nullable)
  external_provider (google|null) · external_id · external_etag
  created_at · updated_at · deleted_at
  INDEX (user_id, start_datetime)

event_reminders
  id · event_id (fk) · minutes_before · sent_at (nullable)
  UNIQUE (event_id, minutes_before)       -- idempotência (RF-80)

categories
  id · user_id (fk) · name · type (expense|income)
  icon · color · is_default · is_active
  UNIQUE (user_id, name, type)

transactions
  id · user_id (fk) · type (expense|income)
  amount (numeric(14,2)) · currency
  description · category_id (fk, nullable)
  date (date) · payment_method (nullable)
  attachment_id (fk, nullable) · source (chat|receipt|import|recurring)
  recurring_rule_id (fk, nullable) · installment_group_id (nullable)
  created_at · updated_at · deleted_at
  INDEX (user_id, date) · INDEX (user_id, category_id, date)

attachments
  id · user_id (fk) · storage_key · mime_type · size_bytes · created_at

budgets                                     -- RF-60
  id · user_id (fk) · category_id (fk) · month · limit_amount

conversations / messages                    -- histórico e contexto (RF-65)
  id · user_id (fk) · channel · role · content · created_at

tool_audit_log                              -- RF-88
  id · user_id (fk) · tool_name · params (jsonb) · result_status
  duration_ms · created_at

notifications_log                           -- RF-80
  id · user_id (fk) · type · reference_id · scheduled_for · sent_at · status
```

**Regras de integridade:**

- Toda tabela de domínio carrega `user_id`; **toda query filtra por `user_id`** (RNF-04).
- Exclusões são **soft delete** (`deleted_at`), permitindo o "desfaz isso" do RF-72.
- Valores monetários usam `numeric(14,2)` — **nunca** float.
- Timestamps de evento em `timestamptz`; o fuso do usuário fica em `users.timezone`.

---

## 7. Regras de Negócio

| ID | Regra |
|---|---|
| RN-01 | Duração padrão de evento sem hora de término: 60 minutos. |
| RN-02 | Data padrão de transação sem data informada: hoje, no fuso do usuário. |
| RN-03 | Transação sem categoria identificada cai em "Outros" e o agente pergunta a categoria correta. |
| RN-04 | Valores negativos são rejeitados; o sinal é definido pelo campo `type`. |
| RN-05 | Evento não pode ter `end_datetime` anterior a `start_datetime`. |
| RN-06 | Conflito de agenda gera **alerta**, nunca bloqueio (RF-18). |
| RN-07 | Operação destrutiva exige confirmação explícita na conversa (RF-67). |
| RN-08 | Dados extraídos de recibo por OCR **sempre** passam por confirmação antes de gravar (RF-36 — Fase 1.5). |
| RN-09 | Semana inicia na segunda-feira para fins de relatório. |
| RN-10 | "Este mês" = do dia 1º até hoje, inclusive. |
| RN-11 | Transação em moeda diferente da padrão é armazenada com sua moeda; conversão fica fora do MVP. |
| RN-12 | Ao remover o vínculo com o Google Calendar, os eventos permanecem locais e perdem `external_id`. |

---

## 8. Requisitos Não-Funcionais

### 8.1 Segurança e Privacidade

| ID | Requisito |
|---|---|
| RNF-01 | A LLM **não** deve ter acesso a credenciais de banco, nem gerar ou executar SQL. |
| RNF-02 | Tokens (Telegram, Google OAuth, chaves de LLM) ficam em variáveis de ambiente / secret manager — nunca no código. |
| RNF-03 | Refresh tokens do Google e demais segredos por usuário devem ser armazenados **criptografados** em repouso. |
| RNF-04 | O `user_id` é **sempre** resolvido no servidor a partir da sessão; a LLM nunca pode informá-lo ou alterá-lo. Toda query é filtrada por `user_id`. |
| RNF-05 | Toda entrada de tool é validada por schema antes de tocar a camada de domínio. |
| RNF-06 | O sistema deve ser resistente a **prompt injection**: conteúdo do usuário (inclusive texto de recibo via OCR) nunca é tratado como instrução com autoridade. |
| RNF-07 | Dados pessoais e financeiros devem ser trafegados sob TLS e o sistema deve atender à LGPD (direito de acesso, exportação e exclusão — RF-05, RF-06). |
| RNF-15 | Logs não devem conter valores de transação, conteúdo de mensagens ou tokens em texto claro. |

### 8.2 Portabilidade

| ID | Requisito |
|---|---|
| RNF-08 | O acesso à LLM deve passar por uma **interface de provider** única. Trocar nuvem → local (Ollama/vLLM) deve exigir apenas configuração, sem alterar tools ou domínio. |
| RNF-09 | A camada de domínio e as tools **não devem importar** o framework de agente. A dependência é unidirecional: agente → tools → domínio → repositório. |
| RNF-10 | A camada de canal deve ser um adapter sobre um formato de mensagem canônico. Adicionar WhatsApp ou Web não deve alterar agente nem domínio. |
| RNF-11 | Os prompts (system prompt, descrições de tools) devem viver em arquivos versionados, fora do código de lógica, para permitir ajuste por modelo. |

### 8.3 Desempenho e Confiabilidade

| ID | Requisito |
|---|---|
| RNF-12 | Resposta a consultas simples em até **5 s** (p95), incluindo a latência da LLM. |
| RNF-13 | O webhook do canal deve responder em até **2 s**, processando de forma assíncrona quando necessário e enviando indicador de "digitando". |
| RNF-14 | O scheduler deve garantir **entrega exatamente uma vez** por notificação (RF-80) e sobreviver a reinício do processo. |
| RNF-16 | Falha da LLM ou de provider externo deve degradar com mensagem clara ao usuário, sem perda de dados já confirmados. |
| RNF-17 | Rate limiting por usuário para conter abuso e custo de API. |
| RNF-18 | O sistema deve registrar custo/tokens por interação para acompanhamento de gasto com LLM. |

### 8.4 Qualidade e Operação

| ID | Requisito |
|---|---|
| RNF-19 | Cobertura de testes automatizados ≥ 80% na camada de domínio e tools, **sem LLM no circuito** (tools testadas diretamente). |
| RNF-20 | Suite de testes de comportamento do agente com casos de exemplo (frases → tool esperada + parâmetros esperados), executável em CI. |
| RNF-21 | Migrations versionadas (Alembic); nenhuma alteração manual de schema. |
| RNF-22 | Logs estruturados (JSON) e healthcheck exposto pela API. |
| RNF-23 | Aplicação containerizada (Docker) com `docker-compose` para desenvolvimento local. |

---

## 9. Roadmap por Fases

### Fase 1 — MVP (Telegram)
- Onboarding, identidade multiusuário, preferências (RF-01 a RF-04)
- Agenda: criar, listar, buscar, atualizar, cancelar (RF-10 a RF-18)
- Sync Google Calendar (RF-20 a RF-22)
- Finanças: registrar despesa/receita **por texto** (RF-30 a RF-35, RF-38 a RF-40)
- Categorias padrão e personalizadas (RF-45 a RF-48)
- Relatórios: período, categoria, saldo, comparação, listagem (RF-50 a RF-59)
- Lembretes, resumo diário e semanal (RF-75 a RF-81)
- Camada de tools consolidada (RF-85 a RF-89)

### Fase 1.5 — Recibo por foto
- OCR e extração multimodal de cupom fiscal (RF-36)
- Armazenamento e vínculo da imagem à transação (RF-37)
- Tool `parse_receipt` e fluxo de confirmação (RN-08)
- Resolve as questões Q-03 (onde guardar a imagem) e Q-04 (retenção)

> **Por que separado:** o OCR depende de decisões de armazenamento e retenção que ainda estão em aberto, e é a única funcionalidade do MVP original que não é pré-requisito de nenhuma outra. Adiá-la encurta o caminho até um bot utilizável sem perder nada estruturalmente.

### Fase 2 — WhatsApp
- Adapter de canal WhatsApp (Cloud API), reutilizando agente e domínio
- Vinculação multi-canal (RF-03)
- Ajustes de formatação de mensagem por canal

### Fase 3 — Web
- API REST/streaming para o frontend
- Autenticação web (e-mail/senha ou OAuth) + vínculo com contas de canal
- Dashboard visual: gráficos de gastos, calendário, edição em tela
- Exportação CSV e orçamentos (RF-60, RF-61)

### Fase 4 — LLM Local
- Implementação do provider Ollama/vLLM sobre a interface do RNF-08
- Avaliação de modelos abertos quanto à qualidade de function calling em português
- Benchmark de acurácia (tool certa + parâmetros certos) contra a suite do RNF-20
- Estratégia de fallback: modelo local como padrão, nuvem como contingência

### Fase 5 — Evoluções
- Transações recorrentes e parceladas (RF-41, RF-42)
- Eventos recorrentes completos (RF-19)
- Orçamentos com alerta (RF-60)
- Importação de extratos CSV/OFX
- Entrada e resposta por áudio

---

## 10. Critérios de Aceite do MVP

| # | Critério |
|---|---|
| CA-01 | Um novo usuário completa o onboarding no Telegram e tem timezone e moeda registrados. |
| CA-02 | "marca dentista quinta às 15h" cria o evento na data correta, com 1h de duração, e aparece no Google Calendar. |
| CA-03 | "o que eu tenho amanhã?" lista corretamente os eventos do dia seguinte, incluindo os criados fora do assistente. |
| CA-04 | "cancela o dentista" pede confirmação e só remove após o "sim". |
| CA-05 | "gastei 45 no mercado ontem" grava despesa de R$ 45,00, data de ontem, categoria Mercado. |
| CA-06 | *(Fase 1.5)* Foto de cupom fiscal gera proposta de transação com valor e data corretos, gravada apenas após confirmação. |
| CA-07 | "quanto gastei esse mês?" retorna o total correto do mês corrente. |
| CA-08 | "quanto gastei com transporte em julho?" retorna o total correto da categoria no mês indicado. |
| CA-09 | "e no mês passado?" logo em seguida é entendido como follow-up da consulta anterior. |
| CA-10 | O lembrete de um compromisso chega uma única vez, 30 minutos antes. |
| CA-11 | O resumo diário chega no horário configurado, no fuso do usuário. |
| CA-12 | Dois usuários distintos não enxergam, em nenhuma consulta, dados um do outro. |
| CA-13 | Nenhuma tool aceita `user_id` vindo da LLM. |
| CA-14 | A suite de tools passa integralmente sem nenhuma chamada a LLM. |

---

## 11. Questões em Aberto

| # | Questão | Impacto |
|---|---|---|
| ~~Q-01~~ | ~~Mecanismo de tools~~ — **RESOLVIDA na v1.0: Opção C** (§3.3). | — |
| ~~Q-02~~ | ~~Provedor de LLM da fase 1~~ — **RESOLVIDA na v1.0: Google Gemini**, atrás da abstração do RNF-08. Reavaliar na Fase 1.5 quanto à qualidade de visão para OCR. | — |
| Q-03 | Onde armazenar as imagens de recibo (S3/R2 × disco local × banco)? **Não bloqueia a Fase 1** — decidir na Fase 1.5. | Infra |
| Q-04 | Política de retenção das imagens de recibo após a extração. **Não bloqueia a Fase 1.** | LGPD e custo |
| Q-05 | Sync com Google Calendar: push notifications (webhook) ou polling? | Complexidade × latência |
| Q-06 | Estratégia de categorização: heurística por palavra-chave, LLM ou modelo treinado com o histórico do usuário? | Qualidade |
| ~~Q-07~~ | ~~Memória de longo prazo — framework ou tabela própria?~~ — **RESOLVIDA na v1.0: tabela própria** (`conversations`/`messages`). O *Harness* do Pydantic AI está em 0.x com API instável, e o RF-65 é Must. Bônus: o histórico vira dado exportável pela LGPD (RF-05). | — |
| Q-08 | Haverá limite de uso / plano pago, dado o custo por token? | Produto |
| Q-09 | Carregar todas as 24 tools em toda requisição ou fazer **carregamento seletivo** por domínio (agenda × finanças)? Afeta custo de token e acurácia da escolha da tool (§3.3.5). | Custo e qualidade |

---

## 12. Glossário

| Termo | Definição |
|---|---|
| **Tool** | Função determinística exposta à LLM com schema tipado; única via de acesso a dados. |
| **Function calling** | Mecanismo pelo qual a LLM devolve a intenção de chamar uma função com parâmetros, em vez de texto. |
| **MCP** | Model Context Protocol — protocolo aberto para expor tools a modelos de forma desacoplada. |
| **Pydantic AI** | Framework Python de agentes escolhido para orquestrar LLM e tools. |
| **Injeção de dependências** | Recurso do Pydantic AI (`deps_type` + `RunContext`) que entrega contexto do servidor às tools sem expô-lo à LLM. É o que garante o RNF-04 por construção. |
| **Canal** | Meio de conversa com o usuário (Telegram, WhatsApp, Web). |
| **Adapter de canal** | Camada que converte mensagens do canal para o formato canônico interno. |
| **Soft delete** | Exclusão lógica via `deleted_at`, preservando o registro. |

---

## 13. Ordem de Implementação

Sequência sugerida para a Fase 1. Cada etapa termina em algo **verificável** — se você não consegue provar que a etapa funcionou, ela não acabou. A ordem foi montada para que o risco maior venha cedo e o retrabalho seja mínimo.

### Etapa 0 — Esqueleto e fundação

- Estrutura de pastas da §3.3.7 criada, ainda vazia
- FastAPI subindo com `/health`
- Postgres em Docker, Alembic configurado
- Verificação em CI do RF-86 (`grep` da §3.3.7) já rodando **desde o primeiro commit**

> **Pronto quando:** `docker compose up` sobe tudo e `/health` responde 200.

### Etapa 1 — Domínio de finanças, sem LLM nenhuma

Comece pelo domínio mais simples e **sem IA no circuito**. Tabelas `users`, `categories`, `transactions`; `FinanceService` com criar, editar, excluir e os relatórios da §4.5; testes unitários cobrindo as regras RN-02, RN-04, RN-09, RN-10.

> **Pronto quando:** os testes do RNF-19 passam e você consegue calcular "gastos de julho por categoria" chamando o serviço direto no Python.

### Etapa 2 — Camada de tools sobre o domínio

`schemas.py` e `registry.py` com as tools de finanças da §5.2 e §5.3. Ainda **sem framework de agente**. Log de auditoria (RF-88) e retorno estruturado de erro (RF-87).

> **Pronto quando:** o CA-14 passa — a suite de tools roda inteira sem nenhuma chamada a LLM.

### Etapa 3 — Agente e o primeiro fluxo de ponta a ponta

Aqui entra o Pydantic AI. Configure o `Deps` com `user_id` (§3.3.3), registre as tools de finanças, escreva o system prompt em arquivo separado (RNF-11) e conecte o Telegram.

Escolha **um único caminho** para atravessar: *"gastei 45 no mercado ontem"* → transação gravada → *"quanto gastei esse mês?"* → resposta correta.

> **Pronto quando:** CA-05 e CA-07 passam pelo Telegram de verdade.

> **Por que essa etapa vem antes da agenda:** é aqui que aparecem as surpresas — qualidade do Gemini em português, formato de data, o modelo inventando parâmetro. Descobrir isso com 7 tools é muito mais barato do que com 24.

### Etapa 4 — Multiusuário para valer

Onboarding (RF-04), `user_channels`, e o teste que mais importa: dois usuários no mesmo banco, nenhum enxergando o outro.

> **Pronto quando:** CA-12 e CA-13 passam, com teste automatizado que falharia se alguém removesse o isolamento.

### Etapa 5 — Domínio de agenda

`events`, `CalendarService`, tools da §5.1, detecção de conflito (RF-18) e `resolve_relative_date`. Mesmo padrão da Etapa 1 → 2 → 3.

> **Pronto quando:** CA-02 (sem a parte do Google), CA-03 e CA-04 passam.

### Etapa 6 — Scheduler

Container separado (RNF-14). Lembretes (RF-75) e resumos (RF-77, RF-78), com a garantia de envio único via `notifications_log` e `event_reminders`.

> **Pronto quando:** CA-10 e CA-11 passam — inclusive reiniciando o container no meio, sem duplicar envio.

### Etapa 7 — Google Calendar

OAuth, cifra do refresh token (RNF-03), sincronização e tratamento de conflito (RF-21). Deixado por último de propósito: é a peça com mais partes móveis e a única que depende de terceiro.

> **Pronto quando:** CA-02 passa completo e um evento criado no celular aparece no CA-03.

### Etapa 8 — Fechamento do MVP

Rate limiting (RNF-17), rastreio de custo (RNF-18), exportação e exclusão de dados (RF-05, RF-06), suite de comportamento do agente (RNF-20), checklist de go-live do `deployment.md`.

---

### Princípios que valem em todas as etapas

| # | Princípio |
|---|---|
| 1 | **Domínio antes de tool, tool antes de agente.** Nunca o contrário — a LLM é a última camada, não a primeira. |
| 2 | **Nenhuma etapa termina sem teste.** O RNF-19 pede 80% em domínio e tools; alcançar isso no fim é muito mais caro que manter durante. |
| 3 | **A verificação do RF-86 roda desde o commit 1.** Ela só protege se nunca for desligada. |
| 4 | **Migrations sempre aditivas.** Adicione coluna, migre dado, remova a antiga num deploy posterior (ver `deployment.md`, §6). |
| 5 | **Descrição de tool é código de produção.** Cada palavra é paga em toda requisição (§3.3.5). |
| 6 | **Ao final de cada etapa, um commit que sobe.** Se não dá para fazer deploy, a etapa não acabou. |
