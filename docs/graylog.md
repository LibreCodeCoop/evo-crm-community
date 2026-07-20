# Graylog on `motoko-new`

This repository is not the Graylog stack itself, but the deployment was
documented alongside Evo CRM because it shares the same host and reverse proxy
infrastructure.

## Deployment target

- host: `motoko-new`
- stack path: `/root/projects/graylog`
- public URL: `https://zo216ergel1t5l5.librecode.coop/`
- shared proxy network: `reverse-proxy`

## Services

The Graylog stack runs these containers:

- `mongodb`
- `datanode`
- `graylog`

The web UI is published through the shared reverse proxy on port `9000`.
Some ingest and internal ports are bound only on `127.0.0.1` for local access
from the host.

## Required environment variables

The deployment relies on the usual proxy metadata plus Graylog-specific
settings:

- `VIRTUAL_HOST`
- `LETSENCRYPT_HOST`
- `LETSENCRYPT_EMAIL`
- `VIRTUAL_PORT`
- `GRAYLOG_HTTP_EXTERNAL_URI`
- `GRAYLOG_PASSWORD_SECRET`
- `GRAYLOG_ROOT_PASSWORD_SHA2`

`GRAYLOG_HTTP_EXTERNAL_URI` must match the public URL exactly.
`GRAYLOG_PASSWORD_SECRET` must stay stable after the first boot.
`GRAYLOG_ROOT_PASSWORD_SHA2` is the actual Graylog admin password hash.

## First boot behavior

On the first start, Graylog exposes a preflight setup page on port `9000`.
The bootstrap log prints a temporary setup password, but that is not the final
Graylog admin password.

## Operational notes

- `GRAYLOG_HTTP_EXTERNAL_URI` must point to the public HTTPS URL, not to
  `localhost`
- the `graylog` service must stay attached to the shared `reverse-proxy`
  network
- the Data Node requires the host to have a sufficient `vm.max_map_count`
  setting
- if port `5555` is already in use on the host, the ingest listener may need to
  be remapped locally

## Files

- [Graylog compose file](../graylog/docker-compose.yml)
- [Graylog environment file](../graylog/.env)
