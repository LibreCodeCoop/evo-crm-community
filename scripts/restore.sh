#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/restore.sh [backup_dir]

Examples:
  scripts/restore.sh
  scripts/restore.sh /var/backups/evo-crm-community/20260615_020000

The script restores:
  - .env, if present in the backup
  - .deploy-secrets.json, if present in the backup
  - database.dump
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_root="$root_dir/backups"

if [[ $# -ge 1 ]]; then
  backup_dir="$1"
else
  if [[ ! -d "$backup_root" ]]; then
    echo "No backups directory found at $backup_root" >&2
    exit 1
  fi

  backup_dir="$(find "$backup_root" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
  if [[ -z "${backup_dir:-}" ]]; then
    echo "No backup directories found in $backup_root" >&2
    exit 1
  fi
fi

if [[ ! -f "$backup_dir/database.dump" ]]; then
  echo "Missing database.dump in $backup_dir" >&2
  exit 1
fi

if [[ -f "$backup_dir/.env" ]]; then
  cp "$backup_dir/.env" "$root_dir/.env"
fi

if [[ -f "$backup_dir/.deploy-secrets.json" ]]; then
  cp "$backup_dir/.deploy-secrets.json" "$root_dir/.deploy-secrets.json"
fi

docker compose --project-directory "$root_dir" -f "$root_dir/docker-compose.yml" up -d evo_postgres

cat "$backup_dir/database.dump" | docker compose --project-directory "$root_dir" -f "$root_dir/docker-compose.yml" exec -T evo_postgres sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner'

docker compose --project-directory "$root_dir" -f "$root_dir/docker-compose.yml" up -d --remove-orphans

echo "Restore completed from $backup_dir"
