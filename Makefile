.PHONY: bootstrap help

SITE_DNS ?=
LETSENCRYPT_EMAIL ?= admin@example.com

help:
	@echo "Targets:"
	@echo "  make bootstrap SITE_DNS=app.example.com [LETSENCRYPT_EMAIL=admin@example.com]"

bootstrap:
	@test -n "$(SITE_DNS)" || (echo "SITE_DNS is required, for example: make bootstrap SITE_DNS=app.example.com" >&2; exit 1)
	@bash scripts/bootstrap.sh "$(SITE_DNS)" "$(LETSENCRYPT_EMAIL)"
