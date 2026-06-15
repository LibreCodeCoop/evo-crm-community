#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/backup.sh [--with-volumes] [backup_root]

Examples:
  scripts/backup.sh
  scripts/backup.sh /var/backups/evo-crm-community
  scripts/backup.sh --with-volumes
  scripts/backup.sh --with-volumes /var/backups/evo-crm-community

The script creates a timestamped backup directory containing:
  - database.dump
  - .env, if present
  - .deploy-secrets.json, if present
  - compose files and a small manifest
  - volume tarballs when --with-volumes is set
EOF
}

with_volumes=false
backup_root=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --with-volumes)
      with_volumes=true
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -n "$backup_root" ]]; then
        echo "Only one backup_root may be provided" >&2
        usage >&2
        exit 1
      fi
      backup_root="$1"
      ;;
  esac
  shift
done

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_root="${backup_root:-$root_dir/backups}"
timestamp="$(date +%Y%m%d_%H%M%S)"
backup_dir="$backup_root/$timestamp"
volumes_dir="$backup_dir/volumes"

mkdir -p "$backup_dir"

if [[ -f "$root_dir/.env" ]]; then
  cp "$root_dir/.env" "$backup_dir/.env"
fi

if [[ -f "$root_dir/.deploy-secrets.json" ]]; then
  cp "$root_dir/.deploy-secrets.json" "$backup_dir/.deploy-secrets.json"
fi

cp "$root_dir/docker-compose.yml" "$backup_dir/docker-compose.yml"
if [[ -f "$root_dir/docker-compose.override.yml" ]]; then
  cp "$root_dir/docker-compose.override.yml" "$backup_dir/docker-compose.override.yml"
fi

if git -C "$root_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  {
    echo "repository=$(git -C "$root_dir" rev-parse --short HEAD)"
    echo "branch=$(git -C "$root_dir" branch --show-current)"
    echo "created_at=$timestamp"
    echo "with_volumes=$with_volumes"
  } > "$backup_dir/manifest.txt"
fi

if ! docker compose --project-directory "$root_dir" -f "$root_dir/docker-compose.yml" exec -T evo_postgres sh -lc \
  'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$backup_dir/database.dump"; then
  echo "database dump failed" >&2
  exit 1
fi

if [[ "$with_volumes" == true ]]; then
  mkdir -p "$volumes_dir"
  project_name="$(basename "$root_dir")"
  volume_names=(
    "${project_name}_evo_postgres_data"
    "${project_name}_evo_redis_data"
    "${project_name}_evo_processor_logs"
    "${project_name}_evo_journeys_mock_data"
    "${project_name}_evo_segments_mock_data"
  )

  for volume_name in "${volume_names[@]}"; do
    if docker volume inspect "$volume_name" >/dev/null 2>&1; then
      docker run --rm \
        -v "${volume_name}:/data:ro" \
        -v "${volumes_dir}:/backup" \
        alpine:3.20 \
        sh -c "cd /data && tar -czf /backup/${volume_name}.tar.gz ."
    fi
  done
fi

echo "Backup written to $backup_dir"
