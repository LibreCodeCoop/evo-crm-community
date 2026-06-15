.PHONY: bootstrap backup restore help

SITE_DNS ?=
LETSENCRYPT_EMAIL ?= admin@example.com
BACKUP_ROOT ?=
BACKUP_DIR ?=
WITH_VOLUMES ?= false

help:
	@echo "Targets:"
	@echo "  make bootstrap SITE_DNS=app.example.com [LETSENCRYPT_EMAIL=admin@example.com]"
	@echo "  make backup [BACKUP_ROOT=/var/backups/evo-crm-community]"
	@echo "  make backup WITH_VOLUMES=true [BACKUP_ROOT=/var/backups/evo-crm-community]"
	@echo "  make restore [BACKUP_DIR=/var/backups/evo-crm-community/20260615_020000]"

bootstrap:
	@test -n "$(SITE_DNS)" || (echo "SITE_DNS is required, for example: make bootstrap SITE_DNS=app.example.com" >&2; exit 1)
	@bash scripts/bootstrap.sh "$(SITE_DNS)" "$(LETSENCRYPT_EMAIL)"

backup:
	@if [ "$(WITH_VOLUMES)" = "true" ]; then \
		if [ -n "$(BACKUP_ROOT)" ]; then bash scripts/backup.sh --with-volumes "$(BACKUP_ROOT)"; else bash scripts/backup.sh --with-volumes; fi; \
	else \
		if [ -n "$(BACKUP_ROOT)" ]; then bash scripts/backup.sh "$(BACKUP_ROOT)"; else bash scripts/backup.sh; fi; \
	fi

restore:
	@bash scripts/restore.sh "$(BACKUP_DIR)"
