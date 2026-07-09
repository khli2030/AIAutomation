# AGENTS.md

## Cursor Cloud specific instructions

### Repository state (read this first)

This repository is **documentation-only** and is at "Step 1 — Project Structure
Proposal" (see `README.md` and `docs/01-project-structure.md`). It contains no
application code, no dependency manifests (`pyproject.toml` / `requirements.txt`
/ `package.json`), no lockfiles, no `docker-compose.yml`, and no tests. As a
result there is currently **nothing to install, lint, test, build, or run**.

The stack described in the docs (FastAPI backend, PostgreSQL, Redis + Celery,
Ansible Runner, Next.js frontend, Docker Compose) is *planned*, not implemented.
Do not assume any of those services exist until the corresponding code and
manifests are actually added in later steps.

### Environment

- Preinstalled tooling in the Cloud VM: Python 3.12, Node.js 22, npm 10.
- Docker is **not** installed. When Step 2 introduces `docker-compose.yml`,
  Docker must be installed before the compose stack can run.

### Working in this repo today

- Editing docs only? No setup is required — just edit the Markdown and open a PR.
- To preview Markdown locally you can render it to HTML with a throwaway tool,
  e.g. `npx -y marked -i docs/01-project-structure.md -o /tmp/preview.html`
  (this uses the npx cache and does not add a repo dependency).

### When code is added in later steps

When backend/frontend code and manifests land, update the startup update script
to install their dependencies (guarded by file existence), and add per-service
run/lint/test/build notes here. Suggested future commands once files exist:

- Backend: `pip install -r backend/requirements.txt` (or `pip install -e backend`
  if `pyproject.toml` is chosen), then `uvicorn app.main:app --reload`.
- Frontend: `npm --prefix frontend install`, then `npm --prefix frontend run dev`.
- Services (Postgres/Redis/worker): via `docker compose up` once Step 2 lands.
