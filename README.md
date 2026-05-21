# evo-crm-community

## Deploy

This repository is designed to run behind a shared `nginx-proxy` stack on the
target VPS. The deployment playbook assumes:

- Docker is already installed on the server.
- The repository exists at `/root/projects/evo-crm-community`.
- The shared proxy stack exists at `/root/projects/nginx-proxy`.

To deploy a new installation, pass only the public DNS name:

```bash
ansible-playbook -i motoko-new, deploy/install.yml -e site_dns=app.example.com
```

The playbook derives the public hosts from `site_dns`:

- frontend: `https://{{ site_dns }}`
- backend: `https://api.{{ site_dns }}`

It also writes the `.env` file, ensures the `reverse-proxy` Docker network
exists, starts the shared proxy stack, starts the app stack, and waits for the
frontend and API health endpoint to respond over HTTPS.

The generated `.env` also sets `CORS_ORIGINS` so the auth and CRM services
accept browser requests from both public hosts:

- `https://{{ site_dns }}`
- `https://api.{{ site_dns }}`
