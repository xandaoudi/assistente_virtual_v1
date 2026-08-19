#!/usr/bin/env bash
# =============================================================================
# deploy.sh — atualiza a aplicação na VPS
# =============================================================================
# Uso, dentro do diretório do projeto na VM:
#   ./scripts/deploy.sh
#
# Faz: backup do banco → git pull → build → migrations → restart → healthcheck,
# com rollback automático se o healthcheck falhar.
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

log()  { echo -e "\n\033[1;34m==>\033[0m $*"; }
ok()   { echo -e "\033[1;32m[ok]\033[0m $*"; }
fail() { echo -e "\033[1;31m[erro]\033[0m $*" >&2; exit 1; }

[[ -f .env ]] || fail ".env não encontrado. Copie de .env.example e preencha."

# --- 1. Backup antes de qualquer coisa ---------------------------------------
log "Backup do banco antes do deploy"
./scripts/backup-db.sh || fail "Backup falhou — deploy abortado."

# --- 2. Guardar a imagem atual para rollback ---------------------------------
PREVIOUS_IMAGE=$(docker image inspect assistente-virtual:latest \
                   --format '{{.Id}}' 2>/dev/null || echo "")
if [[ -n "$PREVIOUS_IMAGE" ]]; then
    docker tag assistente-virtual:latest assistente-virtual:previous
    ok "Imagem anterior marcada como :previous"
fi

# --- 3. Atualizar o código ---------------------------------------------------
log "Puxando alterações do git"
git fetch origin
CURRENT_COMMIT=$(git rev-parse HEAD)
git pull --ff-only origin main
NEW_COMMIT=$(git rev-parse HEAD)

if [[ "$CURRENT_COMMIT" == "$NEW_COMMIT" ]]; then
    echo "Nenhuma alteração nova. Rebuild mesmo assim (pode haver mudança no .env)."
fi

# --- 4. Build ----------------------------------------------------------------
log "Construindo a imagem"
docker compose build api || fail "Build falhou."

# --- 5. Migrations -----------------------------------------------------------
log "Aplicando migrations (Alembic)"
docker compose up -d db
docker compose run --rm api alembic upgrade head \
    || fail "Migration falhou. O banco NÃO foi alterado pelo deploy; restaure o backup se necessário."

# --- 6. Subir ----------------------------------------------------------------
log "Reiniciando os serviços"
docker compose up -d --remove-orphans

# --- 7. Healthcheck com rollback ---------------------------------------------
log "Verificando saúde da aplicação"
HEALTHY=false
for i in {1..30}; do
    if docker compose exec -T api curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    echo "  tentativa $i/30..."
    sleep 3
done

if [[ "$HEALTHY" != "true" ]]; then
    echo -e "\033[1;31m[erro]\033[0m Healthcheck falhou. Últimas linhas do log:"
    docker compose logs --tail=50 api

    if [[ -n "$PREVIOUS_IMAGE" ]]; then
        log "Fazendo rollback para a imagem anterior"
        docker tag assistente-virtual:previous assistente-virtual:latest
        docker compose up -d api scheduler
        echo "Rollback aplicado. ATENÇÃO: migrations já executadas NÃO foram revertidas."
    fi
    exit 1
fi
ok "Aplicação saudável"

# --- 8. Registrar o webhook do Telegram --------------------------------------
log "Registrando o webhook do Telegram"
set -a; source .env; set +a
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    RESPONSE=$(curl -fsS -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
        -d "url=https://${APP_DOMAIN}/webhook/${WEBHOOK_SECRET_PATH}" \
        -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
        -d "max_connections=40" \
        -d "allowed_updates=[\"message\",\"callback_query\"]" || echo "FALHOU")
    echo "  $RESPONSE"
else
    echo "  TELEGRAM_BOT_TOKEN vazio — pulando."
fi

# --- 9. Limpeza --------------------------------------------------------------
log "Removendo imagens órfãs"
docker image prune -f

ok "Deploy concluído — commit $(git rev-parse --short HEAD)"
docker compose ps
