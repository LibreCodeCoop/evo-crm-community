# Backup and restore

This repository uses Docker Compose volumes for runtime data and a host-local
`.env` file plus `.deploy-secrets.json` for configuration. A useful backup
usually includes:

- the Git working tree or a clean checkout of this repository
- `.env`
- `.deploy-secrets.json`
- a PostgreSQL dump

The PostgreSQL dump is the important part for application data. The other files
let you restore the same URLs, passwords, and secret keys.

## Backup files

If you generated the stack with `scripts/bootstrap.sh` or `deploy/install.yml`,
save these files from the repository root:

- `.env`
- `.deploy-secrets.json`
- `docker-compose.yml`
- `docker-compose.override.yml`
- any local edits under `nginx/`, `frontend/`, or the compatibility services

Those source files are already in Git, so in practice a `git clone` plus the two
hidden files is enough for config recovery.

## Dump the database

Use `pg_dump` from inside the PostgreSQL container:

```bash
mkdir -p backups
docker compose exec -T evo_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > backups/evo_community_$(date +%Y%m%d_%H%M%S).dump
```

If you want plain SQL instead of a custom-format dump, drop the `-Fc` flag.

## Automated backup script

For cron jobs, use the bundled helper:

```bash
make backup
```

It writes a timestamped folder under `backups/` with:

- `database.dump`
- `.env`
- `.deploy-secrets.json`
- `docker-compose.yml`
- `docker-compose.override.yml` if present
- `manifest.txt`
- `volumes/` tarballs when `WITH_VOLUMES=true`

You can point it at another directory if you want Duplicati to watch a
different path:

```bash
make backup BACKUP_ROOT=/var/backups/evo-crm-community
```

If you also want the named Docker volumes, enable the extra flag:

```bash
make backup WITH_VOLUMES=true
```

Example cron entry:

```cron
15 2 * * * cd /home/mohr/git/librecode/evo-crm-community && make backup >/tmp/evo-crm-backup.log 2>&1
```

For a fuller snapshot:

```cron
15 2 * * * cd /home/mohr/git/librecode/evo-crm-community && make backup WITH_VOLUMES=true >/tmp/evo-crm-backup.log 2>&1
```

## Restore the database

To restore the latest backup directory created by `make backup`:

```bash
make restore
```

To restore a specific backup directory:

```bash
make restore BACKUP_DIR=/var/backups/evo-crm-community/20260615_020000
```

The script restores `.env` and `.deploy-secrets.json` if they exist, then
restores `database.dump` into PostgreSQL.

If you want to restore a custom-format dump by hand into an empty or reset
database:

```bash
cat backups/evo_community.dump | docker compose exec -T evo_postgres sh -lc 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists'
```

If the target database already contains data, stop the stack first or restore
into a fresh database name.

## Backup the named volumes

If you want a fuller snapshot of runtime state, back up the named volumes as
tarballs. The main one is PostgreSQL:

```bash
mkdir -p backups
docker run --rm \
  -v evo-crm-community_evo_postgres_data:/data \
  -v "$PWD/backups":/backup \
  alpine:3.20 \
  sh -c 'cd /data && tar -czf /backup/evo_postgres_data.tar.gz .'
```

Other volumes in this stack are:

- `evo_redis_data`
- `evo_processor_logs`
- `evo_journeys_mock_data`
- `evo_segments_mock_data`

Redis data is usually disposable if the app can rebuild caches. The mock service
volumes matter only if you want to preserve local compatibility-service data.

The `WITH_VOLUMES=true` mode stores each named volume as a `tar.gz` file under
`volumes/` in the backup directory. That is the mode to use if Duplicati should
capture runtime state beyond the database.

## Restore notes

- Restore `.env` and `.deploy-secrets.json` before starting the stack.
- Use the same `POSTGRES_DATABASE`, `POSTGRES_USERNAME`, and `POSTGRES_PASSWORD`
  values when restoring.
- If you changed hostnames, regenerate `.env` or rerun `scripts/bootstrap.sh`.
- Volume tarballs are optional and only needed if you enabled `WITH_VOLUMES=true`.

## Suggested cadence

- Database dump: daily or before every deploy
- `.env` and `.deploy-secrets.json`: whenever they change
- Volume tarballs: only if you need a full runtime snapshot
