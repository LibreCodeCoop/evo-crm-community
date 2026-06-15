#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap.sh <site_dns> [letsencrypt_email]

Example:
  scripts/bootstrap.sh app.example.com admin@example.com

If a shared nginx-proxy repository is available at ../nginx-proxy or
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 1
fi

site_dns="$1"
letsencrypt_email="${2:-admin@example.com}"

case "$site_dns" in
  http://*|https://*|*/*|"")
    echo "site_dns must be a bare DNS name, for example: app.example.com" >&2
    exit 1
    ;;
esac

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
secrets_file="$root_dir/.deploy-secrets.json"
env_file="$root_dir/.env"

backend_host="api.${site_dns}"
frontend_host="${site_dns}"
backend_url="https://${backend_host}"
frontend_url="https://${frontend_host}"
cors_origins="${frontend_url},${backend_url}"

python3 - "$site_dns" "$letsencrypt_email" "$secrets_file" "$env_file" "$backend_url" "$frontend_url" "$cors_origins" <<'PY'
import json
import pathlib
import secrets
import sys

site_dns = sys.argv[1]
letsencrypt_email = sys.argv[2]
secrets_file = pathlib.Path(sys.argv[3])
env_file = pathlib.Path(sys.argv[4])
backend_url = sys.argv[5]
frontend_url = sys.argv[6]
cors_origins = sys.argv[7]

if not secrets_file.exists():
    values = {
        "POSTGRES_PASSWORD": secrets.token_urlsafe(18),
        "REDIS_PASSWORD": secrets.token_urlsafe(18),
        "SECRET_KEY_BASE": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": secrets.token_urlsafe(32),
        "EVOAI_CRM_API_TOKEN": secrets.token_urlsafe(24),
        "BOT_RUNTIME_SECRET": secrets.token_urlsafe(24),
    }
    values["JWT_SECRET_KEY"] = values["SECRET_KEY_BASE"]
    values["DOORKEEPER_JWT_SECRET_KEY"] = values["SECRET_KEY_BASE"]
    secrets_file.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    secrets_file.chmod(0o600)

values = json.loads(secrets_file.read_text(encoding="utf-8"))

env_lines = [
    f"BACKEND_HOST=api.{site_dns}",
    f"FRONTEND_HOST={site_dns}",
    f"BACKEND_URL={backend_url}",
    f"FRONTEND_URL={frontend_url}",
    f"AUTH_SERVICE_URL={backend_url}",
    f"CORS_ORIGINS={cors_origins}",
    f"LETSENCRYPT_EMAIL={letsencrypt_email}",
    "MAILER_SENDER_EMAIL=no-reply@example.com",
    "POSTGRES_HOST=postgres",
    "POSTGRES_PORT=5432",
    "POSTGRES_USERNAME=postgres",
    f"POSTGRES_PASSWORD={values['POSTGRES_PASSWORD']}",
    "POSTGRES_DATABASE=evo_community",
    f"REDIS_PASSWORD={values['REDIS_PASSWORD']}",
    f"REDIS_URL=redis://:{values['REDIS_PASSWORD']}@redis:6379",
    f"SECRET_KEY_BASE={values['SECRET_KEY_BASE']}",
    f"JWT_SECRET_KEY={values['JWT_SECRET_KEY']}",
    f"DOORKEEPER_JWT_SECRET_KEY={values['DOORKEEPER_JWT_SECRET_KEY']}",
    f"ENCRYPTION_KEY={values['ENCRYPTION_KEY']}",
    f"EVOAI_CRM_API_TOKEN={values['EVOAI_CRM_API_TOKEN']}",
    f"BOT_RUNTIME_SECRET={values['BOT_RUNTIME_SECRET']}",
    "BOT_RUNTIME_URL=http://evo_bot_runtime:8080",
    "BOT_RUNTIME_POSTBACK_BASE_URL=http://evo_crm:3000",
    "EVO_AI_CRM_URL=http://evo_crm:3000",
    "EVO_AUTH_BASE_URL=http://evo_auth:3001",
    "EVOLUTION_BASE_URL=http://evo_crm:3000",
    "AI_PROCESSOR_URL=http://evo_processor:8000",
    "CORE_SERVICE_URL=http://evo_core:5555/api/v1",
    "LISTEN_ADDR=0.0.0.0:8080",
    "AI_CALL_TIMEOUT_SECONDS=30",
    "SMTP_ADDRESS=smtp.mailgun.org",
    "SMTP_PORT=465",
    "SMTP_DOMAIN=example.com",
    "SMTP_AUTHENTICATION=login",
    "SMTP_ENABLE_STARTTLS_AUTO=false",
    "SMTP_SSL=true",
    "SMTP_USERNAME=no-reply@example.com",
    "SMTP_PASSWORD=",
    f"VITE_API_URL={backend_url}",
    f"VITE_AUTH_API_URL={backend_url}",
    f"VITE_EVOAI_API_URL={backend_url}",
    f"VITE_AGENT_PROCESSOR_URL={backend_url}",
]

env_file.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
env_file.chmod(0o600)
PY

docker network inspect reverse-proxy >/dev/null 2>&1 || docker network create reverse-proxy >/dev/null

(cd "$root_dir" && docker compose --env-file .env up -d --remove-orphans)

echo "Stack started."
echo "Frontend: https://${frontend_host}"
echo "Backend:  https://${backend_host}/health/ready"
