"""Real Ansible Runner adapter — Phase 6 only.

IMPORTANT:
- This module must NEVER be imported when MOCK_MODE=true.
- AnsibleExecutionService imports it lazily only after confirming mock_mode is False.
- Do not add subprocess / ansible-runner calls here until Phase 6 is explicitly implemented
  on the internal Ansible control server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.execution_job import ExecutionJob

# Intentionally do NOT import ansible_runner, subprocess, or paramiko at module level.


class RealAnsibleNotImplementedError(RuntimeError):
    """Raised until Phase 6 implements Runner on the internal Ansible host."""


def run_with_ansible_runner(
    *,
    job: ExecutionJob,
    mode: str,
) -> dict[str, Any]:
    """Execute via ansible-runner (not implemented yet).

    Guaranteed not to be called while MOCK_MODE=true because
    AnsibleExecutionService only imports this module when mock_mode is False.
    """
    raise RealAnsibleNotImplementedError(
        f"Real Ansible Runner is not implemented yet (job_id={job.id}, mode={mode}). "
        "Keep MOCK_MODE=true. See DEPLOYMENT.md."
    )
