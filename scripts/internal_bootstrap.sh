#!/usr/bin/env bash
# Bootstrap the internal Docker Compose stack on the Ansible control server.
# Safe defaults: no cloud services, loopback-bound ports, local builds.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> Internal compliance platform bootstrap"
echo "    Root: $ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> Created .env from .env.example — edit secrets before production use"
fi

mkdir -p \
  data/uploads \
  data/ansible_private_data \
  data/tmp_inventories \
  data/ansible-ssh

if [[ ! -f data/ansible-ssh/id_rsa && ! -f data/ansible-ssh/id_ed25519 ]]; then
  echo "==> WARNING: No SSH private key under data/ansible-ssh/"
  echo "    Copy the Ansible control-node key before running remediation jobs:"
  echo "      cp /path/to/ansible_key data/ansible-ssh/id_rsa && chmod 600 data/ansible-ssh/id_rsa"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found. Install Docker Engine from your internal package mirror."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose plugin not found."
  exit 1
fi

echo "==> Building and starting db, redis, backend, celery-worker"
docker compose up -d --build db redis backend celery-worker

echo "==> Waiting for backend health"
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "==> Running migrations"
docker compose exec -T backend alembic upgrade head

echo "==> Seeding remediation_catalog"
docker compose exec -T backend python -m app.db.seed_cli

echo "==> Done"
echo "    API docs:  http://127.0.0.1:8000/docs"
echo "    Health:    http://127.0.0.1:8000/health"
echo "    Reminder:  this stack is internal-only (no AWS / public cloud)."
