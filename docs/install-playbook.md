# Using `deploy/install.yml`

This playbook is the fastest way to install or refresh the stack on a VPS
that already has Docker, the app repository, and the shared proxy repository.

## What it expects

- Docker and Docker Compose installed on the target host
- the application repository at `/root/projects/evo-crm-community`
- the shared proxy repository at `/root/projects/nginx-proxy`
- DNS records pointing the public hostnames to the VPS
- SMTP settings if you want password reset and confirmation email flows to work

## What it does

The playbook:

1. validates the DNS name passed in `site_dns`
2. creates or reuses a host-local `.deploy-secrets.json` file with secrets
3. writes a host-specific `.env` file into the app repository
4. ensures the `reverse-proxy` Docker network exists
5. starts the shared proxy stack
6. starts the Evo CRM stack
7. waits for the frontend and backend health checks over HTTPS

## Basic usage

Run it from your workstation against the target host or inventory:

```bash
ansible-playbook -i motoko-new, deploy/install.yml -e site_dns=app.example.com
```

If you already manage inventory in a file, use that instead:

```bash
ansible-playbook -i inventory.ini deploy/install.yml -e site_dns=app.example.com
```

Use only the bare DNS name in `site_dns`:

- `app.example.com`
- not `https://app.example.com`
- not `app.example.com/login`

The playbook derives the public hosts from that value:

- frontend host: `app.example.com`
- backend host: `api.app.example.com`

## Paths and defaults

By default the playbook looks for:

- `/root/projects/evo-crm-community`
- `/root/projects/nginx-proxy`

If your VPS uses different paths, edit `install_root` and `proxy_root` in
[deploy/install.yml](../deploy/install.yml) before running it.

The playbook also writes the following values into `.env` on the target host:

- `BACKEND_HOST`
- `FRONTEND_HOST`
- `BACKEND_URL`
- `FRONTEND_URL`
- `AUTH_SERVICE_URL`
- `CORS_ORIGINS`
- `LETSENCRYPT_EMAIL`
- `MAILER_SENDER_EMAIL`
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `SECRET_KEY_BASE`
- `JWT_SECRET_KEY`
- `DOORKEEPER_JWT_SECRET_KEY`
- `ENCRYPTION_KEY`
- `EVOAI_CRM_API_TOKEN`
- `BOT_RUNTIME_SECRET`
- `BOT_RUNTIME_URL`
- `BOT_RUNTIME_POSTBACK_BASE_URL`
- `EVO_AI_CRM_URL`
- `EVO_AUTH_BASE_URL`
- `EVOLUTION_BASE_URL`
- `AI_PROCESSOR_URL`
- `CORE_SERVICE_URL`
- `LISTEN_ADDR`
- `AI_CALL_TIMEOUT_SECONDS`
- `SMTP_ADDRESS`
- `SMTP_PORT`
- `SMTP_DOMAIN`
- `SMTP_AUTHENTICATION`
- `SMTP_ENABLE_STARTTLS_AUTO`
- `SMTP_SSL`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `VITE_API_URL`
- `VITE_AUTH_API_URL`
- `VITE_EVOAI_API_URL`
- `VITE_AGENT_PROCESSOR_URL`

The reusable secret values live in `{{ install_root }}/.deploy-secrets.json`
on the target host. Re-running the playbook with the same repository keeps the
same database password and app secrets.

Most installs can keep the defaults in the playbook, but you should change the
SMTP values if the client uses a different mail provider.

## Quick deploy

This is the shortest supported invocation:

```bash
ansible-playbook -i motoko-new, deploy/install.yml -e site_dns=app.example.com
```

## Manual equivalent

If you need to perform the same steps by hand, the playbook is effectively
doing this:

```bash
cd /root/projects/nginx-proxy && docker compose up -d
cd /root/projects/evo-crm-community && docker compose --env-file .env up -d --remove-orphans
```

The playbook adds the network creation and health checks around that sequence.

## Verification

After the playbook finishes, verify the public endpoints:

```bash
curl -k https://app.example.com
curl -k https://api.app.example.com/health/ready
```

If a deploy fails, check:

- DNS points to the correct VPS
- the `reverse-proxy` network exists
- the proxy stack is running
- the app repository exists at the expected path
- the backend logs for boot or migration failures
