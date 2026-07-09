# AIAutomation — Linux Compliance Remediation Platform

Internal platform for managing and executing Linux compliance remediation via an existing on-prem Ansible control server.

**No AWS / no public cloud.** Platform and Ansible Runner are designed to run on the same internal Ansible control host (initial mode).

## Current status

- **Step 1 (this PR):** Project folder/file structure proposal only.
- See [`docs/01-project-structure.md`](docs/01-project-structure.md).

## Planned stack

| Layer | Technology |
|-------|------------|
| Backend | Python FastAPI |
| DB | PostgreSQL |
| Queue | Redis + Celery |
| Automation | Existing Ansible + Ansible Runner |
| Frontend | Next.js (proposed) |
| Deploy | Docker Compose on internal VM |

## Safety principles

- Excel `Remediation` text is **never** executed as a command.
- Only approved playbooks from `ansible/playbooks/` mapped via `remediation_catalog` may run.
- Production requires dry-run success + human approval.
