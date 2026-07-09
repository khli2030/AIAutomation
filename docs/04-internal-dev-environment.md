# Internal development environment (on-prem only)

This platform is designed for an **internal Linux Ansible control server**.
It does **not** use AWS, Azure, GCP, or other public cloud services.

## Target host

| Requirement | Notes |
|-------------|--------|
| Internal Linux VM/server | Already has Ansible installed and SSH access to targets |
| Docker Engine + Docker Compose plugin | Installed from your internal package mirror |
| Disk for Postgres volume + uploads | Local disk only |
| Network | Corporate LAN / VPN only |

## Architecture (MVP)

```text
Internal Ansible Control Server
┌─────────────────────────────────────────────────────────┐
│  Docker Compose (compliance_internal network)           │
│    ├── backend   (FastAPI)      127.0.0.1:8000          │
│    ├── celery-worker            mounts ansible + SSH    │
│    ├── db        (PostgreSQL)   127.0.0.1:5432          │
│    └── redis                    127.0.0.1:6379          │
│                                                         │
│  Host Ansible tree  ──ro──►  /opt/ansible in worker     │
│  Host SSH keys      ──ro──►  /opt/ansible-ssh           │
│                                                         │
│  celery-worker ──SSH──► internal Linux targets          │
└─────────────────────────────────────────────────────────┘
```

Ports bind to **127.0.0.1** by default so they are not exposed on the LAN.
Operators on the same host (or via SSH tunnel / reverse proxy) reach the API.

## One-time setup on the Ansible server

```bash
# 1) Clone / copy the project onto the internal server
cd /opt/compliance-remediation-platform   # example path

# 2) Environment
cp .env.example .env
# Edit secrets: POSTGRES_PASSWORD, SECRET_KEY
# Optionally set ANSIBLE_HOST_DIR=/etc/ansible if you reuse the host inventory

# 3) SSH material for the worker (never commit these files)
mkdir -p data/ansible-ssh
cp /home/ansible/.ssh/id_rsa data/ansible-ssh/id_rsa
chmod 600 data/ansible-ssh/id_rsa
# optional:
# cp /home/ansible/.ssh/known_hosts data/ansible-ssh/known_hosts

# 4) Ensure playbooks/inventories exist under ANSIBLE_HOST_DIR
#    Default: ./ansible in this repository

# 5) Start stack (images built locally on the server)
docker compose up -d --build db redis backend celery-worker

# 6) Migrate + seed catalog
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.db.seed_cli
```

Helper script: `scripts/internal_bootstrap.sh`

## Image / registry policy (air-gapped friendly)

- Prefer building on the Ansible host: `docker compose build`
- Or set `INTERNAL_REGISTRY=registry.corp.local/` and `PYTHON_BASE_IMAGE=...` in `.env`
- Do **not** require AWS ECR, public Docker Hub, or cloud object storage at runtime
- Postgres/Redis image tags can be pre-loaded on the host from your internal mirror

## What is explicitly out of scope

| Not used | Why |
|----------|-----|
| AWS / Azure / GCP | Platform is on-prem |
| S3 / cloud object storage | Uploads stay under `DATA_DIR` on local disk |
| Managed cloud DB/queue | Postgres + Redis run in Compose on the same host |
| Public SaaS AI APIs | `AI_PROVIDER=mock`, `AI_ENABLED=false` by default |
| Cloud agent / Cursor cloud runtime | Dev/runtime target is the internal Ansible server |

## Reaching the API from another internal workstation

Recommended: SSH tunnel to the Ansible host

```bash
ssh -L 8000:127.0.0.1:8000 user@ansible-control.internal
# then open http://127.0.0.1:8000/docs
```

Alternatively set `BIND_ADDRESS=<internal-nic-ip>` behind your corporate firewall / reverse proxy.

## Later: split web platform from Ansible host

Keep domain logic the same; only change where `celery-worker` runs and how it reaches Ansible (SSH jump, AWX/AAP job templates, etc.). MVP stays same-server.

## Verify

```bash
curl -s http://127.0.0.1:8000/health
docker compose ps
docker compose logs -f celery-worker
```
