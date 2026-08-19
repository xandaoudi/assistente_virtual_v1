#!/usr/bin/env bash
# =============================================================================
# restore-db.sh — restaura um dump gerado por backup-db.sh
# =============================================================================
# Uso:  ./scripts/restore-db.sh backups/av_20260818_030000.sql.gz
#
# Um backup que nunca foi restaurado não é um backup. Teste este script pelo
# menos uma vez antes de precisar dele de verdade.
# =============================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_FILE="${1:-}"
[[ -n "$BACKUP_FILE" ]] || { echo "Uso: $0 <arquivo.sql.gz>"; exit 1; }
[[ -f "$BACKUP_FILE" ]] || { echo "[erro] Arquivo não encontrado: $BACKUP_FILE"; exit 1; }

set -a; source .env; set +a

echo "Isto vai SOBRESCREVER o banco '${POSTGRES_DB}' com o conteúdo de:"
echo "  $BACKUP_FILE"
read -rp "Digite 'CONFIRMO' para continuar: " ANSWER
[[ "$ANSWER" == "CONFIRMO" ]] || { echo "Cancelado."; exit 1; }

echo "==> Parando a aplicação (o banco continua de pé)"
docker compose stop api scheduler

echo "==> Restaurando"
gunzip -c "$BACKUP_FILE" | docker compose exec -T db \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1

echo "==> Reaplicando migrations pendentes"
docker compose run --rm api alembic upgrade head

echo "==> Subindo a aplicação"
docker compose up -d

echo "Restauração concluída."
