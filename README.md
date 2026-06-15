# evo-crm-community

This repository contains the full Evo CRM community stack used for local
development, production-style testing, and hosted deployment behind a shared
reverse proxy.

## Deploy

The full deploy guide lives in [docs/deploy.md](docs/deploy.md).
For the playbook itself, see [docs/install-playbook.md](docs/install-playbook.md).

For a quick bootstrap after cloning, use:

```bash
make bootstrap SITE_DNS=app.example.com
```

That target wraps `scripts/bootstrap.sh`, which generates host secrets, writes
`.env`, and starts the stack. If a shared `reverse-proxy` network is missing,
it creates it first. It does not manage the proxy stack itself.

In short, the production flow is:

```bash
ansible-playbook -i motoko-new, deploy/install.yml -e site_dns=app.example.com
```

That playbook:

- writes the environment file for the target host
- creates the shared `reverse-proxy` Docker network when needed
- starts the shared proxy stack
- starts the Evo CRM stack
- waits for the frontend and backend to answer over HTTPS

The stack is designed to expose:

- frontend: `https://{{ site_dns }}`
- backend: `https://api.{{ site_dns }}`

For an approximate footprint of the Docker images used by the stack, see
[docs/image-sizes.md](docs/image-sizes.md).

For proxy routing details, see [nginx/README.md](nginx/README.md).

## Included compatibility services

The journeys screen is currently backed by a local compatibility service in
this repository so newly created journeys persist in the stack and reappear in
the list until the real backend gains native journey storage.

The segments editor uses the same pattern: a local compatibility service keeps
created segments available to the UI until the backend exposes native segment
storage.
