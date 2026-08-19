# Requisitos — Assistente Virtual Pessoal (Agenda + Finanças)

**Projeto:** `assistente_virtual_v1`
**Versão do documento:** 0.1 (rascunho colaborativo)
**Data:** 18/08/2026
**Autor:** Alexandre

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
| UC-06 | Registrar despesa por foto | *(envia foto do cupom fiscal)* |
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
│  CAMADA DE AGENTE  —  Agno                                     │
│  system prompt, histórico de sessão, memória,                  │
│  seleção e chamada de tools, redação da resposta               │
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
| Orquestração de agente | **Agno** | Agent + Tools + Memory + Session storage |
| Banco de dados | **PostgreSQL 16+** | relacional + JSONB; `pgvector` opcional para memória semântica |
| ORM / migrations | SQLAlchemy 2.x + Alembic | |
| Validação | Pydantic v2 | schemas de tools e DTOs |
| Scheduler | APScheduler (MVP) → Celery/Redis (escala) | ver RNF-14 |
| LLM (fase 1) | Provedor em nuvem via abstração | OpenAI / Gemini / Anthropic |
| LLM (fase futura) | Modelo local via Ollama / vLLM | requisito RNF-08 |
| Canal (fase 1) | Telegram Bot API (webhook) | |

> **Nota sobre Agno:** o Agno fornece o `Agent`, o registro de tools, memória e persistência de sessão, e serve sobre FastAPI. Ele é a implementação escolhida da camada de agente, mas o desenho mantém a **fronteira de tools** independente do framework — os serviços de domínio não importam nada de Agno (ver RNF-09).

### 3.3 Mecanismo de chamada de tools — decisão em aberto

O **contrato das tools** (nome, parâmetros, tipos, retorno, erros) é definido neste documento e é **obrigatório**. O **mecanismo de exposição** dessas tools para a LLM fica em aberto e será decidido na fase de design técnico. Opções consideradas:

| Opção | Prós | Contras |
|---|---|---|
| **A — Function calling nativo via Agno** | Menos peças móveis; caminho natural do framework | Acoplado ao processo do agente |
| **B — Servidor MCP separado** | Desacoplado; reaproveitável por outros clientes (Claude Desktop, IDEs); facilita testar tools isoladamente | Uma camada de rede e deploy a mais |
| **C — Híbrido** | Serviços de domínio expostos como HTTP interno, com adapters finos para function calling **e** MCP | Mais código de fronteira |

**Requisito derivado:** a implementação das tools deve ser escrita como funções Python puras com schema Pydantic, de modo que expor via Agno, via MCP ou via HTTP seja apenas um adapter — sem reescrever lógica. (Ver RF-86 e RNF-09.)

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
| RF-36 | Registrar despesa a partir de **foto de recibo/nota fiscal** (OCR + extração multimodal), apresentando os dados extraídos para confirmação do usuário **antes** de gravar. | Must |
| RF-37 | Anexar a imagem original à transação criada por foto, para consulta posterior. | Should |
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
| `parse_receipt` | `attachment_id` | campos extraídos + `confidence` (**não persiste** — RF-36) |

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
| RN-08 | Dados extraídos de recibo por OCR **sempre** passam por confirmação antes de gravar (RF-36). |
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
- Finanças: registrar despesa/receita por texto e por foto (RF-30 a RF-39)
- Categorias padrão e personalizadas (RF-45 a RF-48)
- Relatórios: período, categoria, saldo, comparação, listagem (RF-50 a RF-59)
- Lembretes, resumo diário e semanal (RF-75 a RF-81)
- Camada de tools consolidada (RF-85 a RF-89)

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
| CA-06 | Foto de cupom fiscal gera proposta de transação com valor e data corretos, gravada apenas após confirmação. |
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
| Q-01 | Mecanismo de tools: function calling via Agno, servidor MCP ou híbrido? (seção 3.3) | Arquitetura |
| Q-02 | Provedor de LLM da fase 1 (OpenAI / Gemini / Anthropic) — critério: qualidade de function calling em PT-BR × custo × visão para OCR. | Custo e qualidade |
| Q-03 | Onde armazenar as imagens de recibo (S3/R2 × disco local × banco)? | Infra |
| Q-04 | Política de retenção das imagens de recibo após a extração. | LGPD e custo |
| Q-05 | Sync com Google Calendar: push notifications (webhook) ou polling? | Complexidade × latência |
| Q-06 | Estratégia de categorização: heurística por palavra-chave, LLM ou modelo treinado com o histórico do usuário? | Qualidade |
| Q-07 | Modelo de memória de longo prazo do usuário (preferências aprendidas) — usar memória do Agno ou tabela própria? | Escopo |
| Q-08 | Haverá limite de uso / plano pago, dado o custo por token? | Produto |

---

## 12. Glossário

| Termo | Definição |
|---|---|
| **Tool** | Função determinística exposta à LLM com schema tipado; única via de acesso a dados. |
| **Function calling** | Mecanismo pelo qual a LLM devolve a intenção de chamar uma função com parâmetros, em vez de texto. |
| **MCP** | Model Context Protocol — protocolo aberto para expor tools a modelos de forma desacoplada. |
| **Agno** | Framework Python de agentes escolhido para orquestrar LLM, tools, memória e sessão. |
| **Canal** | Meio de conversa com o usuário (Telegram, WhatsApp, Web). |
| **Adapter de canal** | Camada que converte mensagens do canal para o formato canônico interno. |
| **Soft delete** | Exclusão lógica via `deleted_at`, preservando o registro. |
