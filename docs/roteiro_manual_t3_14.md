# Roteiro de verificação manual — T3.14

Prova, no Telegram real, dos critérios de aceite de saída da Etapa 3: **CA-05**, **CA-07**,
**CA-09** e a idempotência do T2.11/T3.7. A versão automatizada deste mesmo roteiro (com
`FunctionModel` e Telegram dublado, contra Postgres real) está em
`tests/integration/test_telegram_ca05_ca07_ca09.py` — ela prova que a fiação nunca quebra;
esta execução manual prova que funciona **hoje**, com o Gemini de verdade. As duas são
necessárias (RNF-35).

## Pré-requisitos

1. **Bot do Telegram**: crie um (ou reutilize um existente) via [@BotFather](https://t.me/BotFather)
   — `/newbot`, escolha nome e username, guarde o token gerado.
2. **`.env`** com:
   ```
   TELEGRAM_MODE=polling
   TELEGRAM_BOT_TOKEN=<token do BotFather>
   ```
   (`GOOGLE_API_KEY`, `DATABASE_URL` e `LLM_MODEL` já devem estar configurados — ver `.env.example`.)
3. **Postgres de dev de pé e migrado**:
   ```
   docker compose -f docker-compose.dev.yml up -d
   uv run alembic upgrade head
   ```
4. **Poller rodando** (processo próprio — nunca dentro da API, ver T3.6):
   ```
   uv run python -m app.telegram_poller
   ```
5. Abra uma conversa com o bot no Telegram (a partir do seu usuário, um `chat_id` novo —
   isso exercita a criação de conta pela T3.8, com as categorias padrão do RF-45).

## Roteiro

Envie as mensagens abaixo, uma de cada vez, esperando a resposta antes de mandar a próxima.

| # | Mensagem | Esperado | CA/RF |
|---|---|---|---|
| 1 | `gastei 45 no mercado ontem` | Confirma o registro (valor, data, categoria). | CA-05 |
| 2 | `quanto gastei esse mês?` | Total do mês corrente inclui os R$ 45,00. | CA-07 |
| 3 | `e no mês passado?` | Entendido como follow-up — não pergunta "o quê no mês passado?", já sabe que é sobre gastos. | CA-09 |
| 4 | `qual a capital da França?` | Recusa educada, redirecionando para finanças/agenda — não responde "Paris". | RF-70 |
| 5 | `gastei 45 no mercado ontem` (repetida) | Confirma de novo, mas **não duplica** o lançamento. | T2.11 |

## Verificação no banco (depois do passo 1, e de novo depois do passo 5)

```sql
-- Ajuste o filtro pelo seu external_id (chat_id do Telegram) se necessário.
SELECT t.id, t.type, t.amount, t.date, c.name AS categoria
FROM transactions t
LEFT JOIN categories c ON c.id = t.category_id
JOIN user_channels uc ON uc.user_id = t.user_id
WHERE uc.channel = 'telegram'
ORDER BY t.created_at DESC;
```

Esperado: **uma única linha**, `amount = 45.00`, `type = expense`, categoria `Mercado`, mesmo
depois do passo 5.

## Registro do resultado (para o PR)

Preencha e cole no PR:

```
- [ ] Passo 1 (CA-05): OK / FALHOU — <observação, se houver>
- [ ] Passo 2 (CA-07): OK / FALHOU — <observação>
- [ ] Passo 3 (CA-09): OK / FALHOU — <observação>
- [ ] Passo 4 (RF-70): OK / FALHOU — <observação>
- [ ] Passo 5 (idempotência): OK / FALHOU — <observação>
- [ ] Consulta ao banco confere: 1 transação, R$ 45,00, categoria Mercado
- Data da execução:
- Modelo usado (LLM_MODEL):
```
