# Evo CRM Community Deploy Guide

This repository is meant to run behind a shared reverse proxy. The target
layout is:

- a public TLS-terminating proxy stack at `/root/projects/nginx-proxy`
- this application stack at `/root/projects/evo-crm-community`
- public frontend and API hostnames mapped through the proxy

The deploy playbook and compose files are already wired for this model.

## Topology

The app stack exposes two public entrypoints:

- frontend: `https://<site_dns>`
- backend: `https://api.<site_dns>`

Internally, the stack still uses service names and private Docker networking.
The reverse proxy only sees the public hostnames.

## Prerequisites

- Docker and Docker Compose installed on the target host
- the shared reverse proxy repository present at `/root/projects/nginx-proxy`
- this repository present at `/root/projects/evo-crm-community`
- DNS records pointing the chosen hostnames to the server
- valid SMTP settings if you want password reset and confirmation email flows

The deployment assumes the proxy stack and this app stack share a Docker
network named `reverse-proxy`.

## What the playbook does

The install playbook is [deploy/install.yml](../deploy/install.yml). It:

1. validates the requested DNS name
2. creates or reuses a host-local `.deploy-secrets.json` file with secrets
3. writes a host-specific `.env` file
4. ensures the shared `reverse-proxy` network exists
5. starts the shared proxy stack
6. starts this repository's app stack
7. waits for the frontend and backend health checks over HTTPS

## Quick deploy

Use only the public DNS name, without `http://` or a path:

```bash
ansible-playbook -i motoko-new, deploy/install.yml -e site_dns=app.example.com
```

If you are bootstrapping a fresh clone locally or on a server where the app
repository is already present, you can use the bundled script instead:

```bash
make bootstrap SITE_DNS=app.example.com
```

The playbook derives the public hosts from `site_dns`:

- frontend host: `app.example.com`
- backend host: `api.app.example.com`

## Manual deploy

If you need to deploy by hand, the equivalent sequence is:

```bash
cd /root/projects/evo-crm-community
docker network inspect reverse-proxy >/dev/null 2>&1 || docker network create reverse-proxy
cd /root/projects/evo-crm-community && docker compose --env-file .env up -d --remove-orphans
```

The `.env` file must set at least:

- `BACKEND_HOST`
- `FRONTEND_HOST`
- `BACKEND_URL`
- `FRONTEND_URL`
- `AUTH_SERVICE_URL`
- `CORS_ORIGINS`
- `LETSENCRYPT_EMAIL`

The install playbook also fills in the shared database passwords, app secrets,
bot runtime secret, and the frontend `VITE_*` URLs so the deployed stack boots
with a complete configuration.

The generated secret values are stored on the target host in
`/root/projects/evo-crm-community/.deploy-secrets.json` and reused on future
runs.

## Important environment variables

The repository ships with [`.env.example`](../.env.example). The most important
values for a reverse-proxy deployment are:

| Variable | Purpose |
| --- | --- |
| `BACKEND_HOST` | Public hostname for the API gateway, usually `api.<site_dns>` |
| `FRONTEND_HOST` | Public hostname for the UI |
| `BACKEND_URL` | Public URL the backend uses when generating absolute links |
| `FRONTEND_URL` | Public UI URL used by auth redirects and browser-facing links |
| `AUTH_SERVICE_URL` | Public auth URL exposed to the browser |
| `CORS_ORIGINS` | Allowed browser origins, usually frontend plus backend hosts |
| `LETSENCRYPT_EMAIL` | Email used by the shared proxy for TLS issuance |

The frontend image is configured through build-time Vite variables, while the
backend services consume runtime environment variables. Keep the public URLs
consistent across both layers.

## Reverse proxy requirements

The shared proxy stack must:

- listen on the same Docker network as this app stack
- route `BACKEND_HOST` to the API gateway service on port `3030`
- route `FRONTEND_HOST` to the frontend container on port `80`
- terminate TLS for both hostnames

The gateway and frontend containers in this repository already publish the
required proxy metadata via `VIRTUAL_HOST`, `VIRTUAL_PORT`, and
`LETSENCRYPT_HOST`.

## Health checks

After deploy, verify these URLs:

```bash
curl -k https://app.example.com
curl -k https://api.app.example.com/health/ready
```

If either one fails, check:

- DNS points to the right host
- the `reverse-proxy` network exists
- the proxy stack is running
- the backend service logs for boot or migration failures

## Common problems

### 502 Bad Gateway

Usually means one of these:

- the shared proxy cannot reach the app container
- the `reverse-proxy` network is missing
- the hostname in `VIRTUAL_HOST` does not match the public DNS name
- the upstream service name changed and the proxy is still pointing at the old one

### Browser CORS errors

Usually means `CORS_ORIGINS` does not include both public hosts. Make sure the
frontend origin and the backend origin are listed in the generated `.env`.

### Login or email links use localhost

That means one of the public URL variables is still set to a local value. In a
real deploy, replace the localhost defaults with the actual public domains.

## Related docs

- [nginx/README.md](../nginx/README.md) for the backend gateway routing table
- [deploy/install.yml](../deploy/install.yml) for the Ansible flow
- [docs/install-playbook.md](install-playbook.md) for playbook usage details
- [docker-compose.yml](../docker-compose.yml) for the full service topology
