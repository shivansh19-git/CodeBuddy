# Public Deployment Guide

> This guide covers production hosting for **Agentic Software Engineer**.
> For local development, follow the quick-start steps in [README.md](README.md).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Secret Management](#2-secret-management)
3. [Build the Sandbox Image](#3-build-the-sandbox-image)
4. [Start the Stack with Docker Compose](#4-start-the-stack-with-docker-compose)
5. [Reverse Proxy & HTTPS](#5-reverse-proxy--https)
6. [Resource Limits & Hardening](#6-resource-limits--hardening)
7. [Updating the Application](#7-updating-the-application)
8. [Environment Variable Reference](#8-environment-variable-reference)

---

## 1. Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Docker Engine | 24.x | Required for the test sandbox |
| Docker Compose | v2.x (`docker compose`) | Ships with Docker Desktop |
| A public server | — | Linux recommended (Ubuntu 22.04+) |
| API key | HuggingFace **or** Mistral | At least one provider must be configured for code generation |

> [!IMPORTANT]
> Tests are executed inside Docker containers on the **host** machine.
> The `api` container needs access to the Docker socket (`/var/run/docker.sock`).
> Review your security posture before granting this on a shared host.

---

## 2. Secret Management

API keys and credentials are **never** stored in source code or the Compose file.
Inject them through environment variables only.

### Option A — `.env` file (single server, simplest)

```bash
cp .env.example .env
# Edit .env and fill in your keys:
nano .env
```

Example `.env` (fill in real values):

```ini
HUGGINGFACE_API_KEY=hf_xxxxxxxxxxxxxxxxxxxx
MISTRAL_API_KEY=                        # leave blank if not used
APP_ENV=production
```

> [!CAUTION]
> Never commit `.env` to version control. It is already listed in `.gitignore`.

### Option B — Host environment variables (CI/CD, Docker secrets, Vault)

Export variables on the host before running `docker compose`:

```bash
export HUGGINGFACE_API_KEY="hf_xxxx"
docker compose up -d
```

Or use Docker secrets / your cloud provider's secret store and inject them at
container startup via an entrypoint wrapper.

---

## 3. Build the Sandbox Image

The test-executor image must exist on the host before the API can run tests:

```bash
# From the repository root:
docker build -t agentic-python-sandbox ./docker
```

This image has **no network** and runs only `pytest`. Rebuild it whenever you
update the `docker/Dockerfile`.

---

## 4. Start the Stack with Docker Compose

```bash
# From the repository root:
docker compose -f docker/docker-compose.yml up -d --build
```

| Service | Default URL |
|---|---|
| FastAPI backend | `http://localhost:8000` |
| Streamlit UI | `http://localhost:8501` |
| Health check | `http://localhost:8000/health` |

Check service health:

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f api
```

Stop the stack:

```bash
docker compose -f docker/docker-compose.yml down
```

---

## 5. Reverse Proxy & HTTPS

For public hosting, place a reverse proxy in front of both services.

### Nginx example (minimal)

```nginx
server {
    listen 443 ssl;
    server_name your-domain.example.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.example.com/privkey.pem;

    # Streamlit UI
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # FastAPI backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Use [Certbot](https://certbot.eff.org/) or [Caddy](https://caddyserver.com/) for
automatic TLS certificate provisioning.

---

## 6. Resource Limits & Hardening

### Docker Compose resource limits

Add a `deploy` section to each service in `docker/docker-compose.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: 1G
  ui:
    deploy:
      resources:
        limits:
          cpus: "1"
          memory: 512M
```

### Application-level limits (`.env`)

| Variable | Recommended production value | Purpose |
|---|---|---|
| `MAX_CONCURRENT_TASKS` | `2` | Prevents runaway parallel LLM calls |
| `REQUEST_LIMIT_PER_MINUTE` | `60` | Per-IP throttle |
| `WORKSPACE_TTL_HOURS` | `24` | Automatic workspace cleanup |
| `TEST_TIMEOUT_SECONDS` | `120` | Caps Docker sandbox wall time |
| `MAX_REPOSITORY_SIZE_MB` | `20` | Upload size guard |

### Security checklist

- [ ] API keys are in environment variables, never in source code
- [ ] `.env` is excluded from version control (`.gitignore`)
- [ ] Docker socket access is granted only to the `api` service
- [ ] HTTPS is enforced by the reverse proxy
- [ ] The sandbox image runs with `--network none` (set by the application)
- [ ] `APP_ENV=production` disables debug stack traces in responses

---

## 7. Updating the Application

```bash
# Pull latest code
git pull

# Rebuild images and restart services with zero manual downtime
docker compose -f docker/docker-compose.yml up -d --build

# Rebuild the sandbox image if docker/Dockerfile changed
docker build -t agentic-python-sandbox ./docker
```

To roll back to the previous image:

```bash
# Tag the current image before updating
docker tag agentic-software-engineer-api agentic-software-engineer-api:previous

# Restore if the update fails
docker tag agentic-software-engineer-api:previous agentic-software-engineer-api
docker compose -f docker/docker-compose.yml up -d
```

---

## 8. Environment Variable Reference

All variables below can be set in `.env` or as host environment variables.
See [`.env.example`](.env.example) for a full annotated template.

| Variable | Default | Required | Description |
|---|---|---|---|
| `HUGGINGFACE_API_KEY` | — | One of these | HuggingFace Inference API key |
| `MISTRAL_API_KEY` | — | One of these | Mistral API key |
| `HUGGINGFACE_MODEL` | `Qwen/Qwen2.5-Coder-32B-Instruct` | No | Model for code generation |
| `MISTRAL_MODEL` | `codestral-latest` | No | Mistral model ID |
| `APP_ENV` | `development` | No | Set to `production` for deployment |
| `SANDBOX_IMAGE` | `agentic-python-sandbox` | No | Docker image name for test executor |
| `DATABASE_PATH` | `./data/app.db` | No | SQLite file path |
| `WORKSPACE_ROOT` | `./data/workspaces` | No | Uploaded repository storage |
| `MAX_CONCURRENT_TASKS` | `2` | No | Parallel task cap |
| `REQUEST_LIMIT_PER_MINUTE` | `120` | No | Per-IP rate limit |
| `WORKSPACE_TTL_HOURS` | `24` | No | Hours before workspaces are cleaned |
| `TEST_TIMEOUT_SECONDS` | `120` | No | Max Docker sandbox runtime |
| `MAX_REPOSITORY_SIZE_MB` | `20` | No | Max upload size |
| `API_PORT` | `8000` | No | Host port for the FastAPI service |
| `UI_PORT` | `8501` | No | Host port for the Streamlit service |
