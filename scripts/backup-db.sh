#!/usr/bin/env bash
# =============================================================================
# backup-db.sh — dump do PostgreSQL com rotação
# =============================================================================
# Uso manual:      ./scripts/backup-db.sh
# Uso automático:  ver deployment.md §8.1 (cron diário)
#
# Guarda os dumps em ./backups, comprimidos, mantendo RETENTION_DAYS dias.
# Se OCI_BACKUP_BUCKET estiver definido no .env, envia também para o Object
# Storage da Oracle (10 GB gratuitos) — porque backup que mora só na mesma VM
# não protege contra a perda da VM.
# =============================================================================

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)

[[ -f .env ]] || { echo "[erro] .env não encontrado."; exit 1; }
set -a; source .env; set +a

mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/av_${TIMESTAMP}.sql.gz"

echo "==> Gerando dump: $BACKUP_FILE"

if ! docker compose ps db --status running --quiet | grep -q .; then
    echo "[erro] O container do banco não está rodando."
    exit 1
fi

docker compose exec -T db \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
    | gzip -9 > "$BACKUP_FILE"

# Um dump válido nunca é minúsculo — pega o caso de "pg_dump falhou mas o pipe
# retornou 0" e o arquivo saiu vazio.
SIZE=$(stat -c%s "$BACKUP_FILE")
if [[ "$SIZE" -lt 1024 ]]; then
    echo "[erro] Backup suspeito: apenas ${SIZE} bytes. Removendo."
    rm -f "$BACKUP_FILE"
    exit 1
fi
echo "    ok — $(numfmt --to=iec-i --suffix=B "$SIZE")"

# --- Verificação de integridade do gzip --------------------------------------
gzip -t "$BACKUP_FILE" || { echo "[erro] Arquivo corrompido."; rm -f "$BACKUP_FILE"; exit 1; }

# --- Anexos (recibos) --------------------------------------------------------
MEDIA_BACKUP="${BACKUP_DIR}/media_${TIMESTAMP}.tar.gz"
echo "==> Gerando backup dos anexos"
docker run --rm \
    -v assistente-virtual_media:/media:ro \
    -v "$(realpath "$BACKUP_DIR")":/backup \
    alpine tar czf "/backup/$(basename "$MEDIA_BACKUP")" -C /media . 2>/dev/null \
    || echo "    (sem anexos ainda)"

# --- Cópia externa (opcional) ------------------------------------------------
if [[ -n "${OCI_BACKUP_BUCKET:-}" ]] && command -v oci &>/dev/null; then
    echo "==> Enviando para o Object Storage da Oracle"
    oci os object put --bucket-name "$OCI_BACKUP_BUCKET" \
        --file "$BACKUP_FILE" --name "db/$(basename "$BACKUP_FILE")" \
        --force >/dev/null && echo "    ok"
fi

# --- Rotação -----------------------------------------------------------------
echo "==> Removendo backups com mais de ${RETENTION_DAYS} dias"
find "$BACKUP_DIR" -name 'av_*.sql.gz'     -mtime "+${RETENTION_DAYS}" -delete -print
find "$BACKUP_DIR" -name 'media_*.tar.gz'  -mtime "+${RETENTION_DAYS}" -delete -print

echo "==> Backups atuais:"
ls -lh "$BACKUP_DIR" | tail -n +2
