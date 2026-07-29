"""Phase 11B — SSH-delegated Ansible execution on INFRA-OPS control node.

When REAL_ANSIBLE_EXECUTION_MODE=ssh_delegate, the local app never runs
ansible-runner. It SSHes to the configured control node (BatchMode=yes) and
runs ansible / ansible-playbook there.

Safety:
- Never logs or returns private key contents / secrets.
- Keeps all existing allowlist / pilot / stub / high-risk gates upstream.
- Check-mode only for playbooks (--check).
- No real apply endpoint.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.services.ansible_safety import RealAnsibleBlockedError
from app.services.lab_ansible_config import resolve_auth_mode

logger = logging.getLogger(__name__)


def resolve_execution_mode(settings: Settings) -> str:
    if hasattr(settings, "real_ansible_execution_mode_normalized"):
        return settings.real_ansible_execution_mode_normalized
    mode = str(
        getattr(settings, "real_ansible_execution_mode", "local") or "local"
    ).strip().lower()
    return mode if mode in {"local", "ssh_delegate"} else "local"


def control_node_host(settings: Settings) -> str:
    return (getattr(settings, "real_ansible_control_node_host", None) or "").strip()


def control_node_user(settings: Settings) -> str:
    return (getattr(settings, "real_ansible_control_node_user", None) or "").strip()


def control_node_workdir(settings: Settings) -> str:
    return (getattr(settings, "real_ansible_control_node_workdir", None) or "").strip()


def control_node_timeout(settings: Settings) -> int:
    try:
        n = int(
            getattr(settings, "real_ansible_control_node_timeout_seconds", 120) or 120
        )
    except (TypeError, ValueError):
        return 120
    return max(10, min(600, n))


def control_node_configured(settings: Settings) -> bool:
    return bool(control_node_host(settings) and control_node_workdir(settings))


def ssh_client_available() -> tuple[bool, str]:
    path = shutil.which("ssh")
    if not path:
        return False, "ssh client not found on PATH (required for ssh_delegate)"
    return True, "ssh client available"


def delegate_blocking_reasons(settings: Settings) -> list[str]:
    """Reasons ssh_delegate cannot run (config only — no secrets)."""
    reasons: list[str] = []
    if resolve_execution_mode(settings) != "ssh_delegate":
        return reasons
    if not control_node_host(settings):
        reasons.append(
            "REAL_ANSIBLE_CONTROL_NODE_HOST missing "
            "(required when REAL_ANSIBLE_EXECUTION_MODE=ssh_delegate)"
        )
    if not control_node_workdir(settings):
        reasons.append(
            "REAL_ANSIBLE_CONTROL_NODE_WORKDIR missing "
            "(required when REAL_ANSIBLE_EXECUTION_MODE=ssh_delegate)"
        )
    ok, detail = ssh_client_available()
    if not ok:
        reasons.append(detail)
    return reasons


def delegate_available(settings: Settings) -> bool:
    if resolve_execution_mode(settings) != "ssh_delegate":
        return False
    return not delegate_blocking_reasons(settings)


def _reject_unsafe_token(value: str, *, label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise RealAnsibleBlockedError(
            f"{label} is empty", code="ssh_delegate_invalid"
        )
    if any(ch in text for ch in ("\n", "\r", "\x00")):
        raise RealAnsibleBlockedError(
            f"{label} contains invalid characters", code="ssh_delegate_invalid"
        )
    return text


def build_ssh_argv(
    settings: Settings,
    *,
    remote_command: str,
) -> list[str]:
    """Build local ssh argv. Never includes private key contents."""
    host = _reject_unsafe_token(
        control_node_host(settings), label="REAL_ANSIBLE_CONTROL_NODE_HOST"
    )
    workdir = _reject_unsafe_token(
        control_node_workdir(settings), label="REAL_ANSIBLE_CONTROL_NODE_WORKDIR"
    )
    _ = workdir  # validated separately by callers that embed workdir in remote_command
    user = control_node_user(settings)
    target = f"{user}@{host}" if user else host
    timeout = min(30, control_node_timeout(settings))
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        target,
        remote_command,
    ]
    return argv


def build_remote_shell_command(workdir: str, argv_parts: list[str]) -> str:
    """Safe remote shell: cd workdir && quoted argv parts."""
    wd = _reject_unsafe_token(workdir, label="REAL_ANSIBLE_CONTROL_NODE_WORKDIR")
    if not argv_parts:
        raise RealAnsibleBlockedError(
            "empty remote command", code="ssh_delegate_invalid"
        )
    quoted = " ".join(shlex.quote(p) for p in argv_parts)
    return f"cd {shlex.quote(wd)} && {quoted}"


def build_remote_ping_argv(
    settings: Settings,
    *,
    hosts: list[str],
    inventory_path: str,
) -> list[str]:
    """ansible module=ping argv (runs on control node)."""
    inv = _reject_unsafe_token(inventory_path, label="inventory path")
    host_pattern = ",".join(
        _reject_unsafe_token(h, label="host") for h in hosts if h and str(h).strip()
    )
    if not host_pattern:
        raise RealAnsibleBlockedError(
            "no hosts for delegated ping", code="ssh_delegate_invalid"
        )
    parts = ["ansible", "-i", inv, host_pattern, "-m", "ping"]
    auth_mode = resolve_auth_mode(settings)
    if auth_mode == "explicit":
        user = (settings.real_ansible_remote_user or "").strip()
        key = (settings.real_ansible_private_key_path or "").strip()
        if user:
            parts.extend(["-u", user])
        if key:
            # Path on control node only — never key material.
            parts.extend(["--private-key", key])
    return parts


def build_remote_playbook_check_argv(
    settings: Settings,
    *,
    playbook_rel: str,
    inventory_path: str,
    limit_hosts: list[str],
) -> list[str]:
    """ansible-playbook --check argv (runs on control node)."""
    inv = _reject_unsafe_token(inventory_path, label="inventory path")
    rel = _reject_unsafe_token(playbook_rel, label="playbook path")
    # Catalog paths are filenames under ansible/playbooks on the control node repo.
    remote_playbook = rel if "/" in rel else f"ansible/playbooks/{rel}"
    limit = ",".join(
        _reject_unsafe_token(h, label="host")
        for h in limit_hosts
        if h and str(h).strip()
    )
    if not limit:
        raise RealAnsibleBlockedError(
            "no allowlisted hosts for delegated dry-run",
            code="host_not_allowlisted",
        )
    parts = [
        "ansible-playbook",
        "-i",
        inv,
        remote_playbook,
        "--check",
        "--limit",
        limit,
    ]
    auth_mode = resolve_auth_mode(settings)
    if auth_mode == "explicit":
        user = (settings.real_ansible_remote_user or "").strip()
        key = (settings.real_ansible_private_key_path or "").strip()
        if user:
            parts.extend(["--user", user])
        if key:
            parts.extend(["--private-key", key])
    return parts


def redact_for_log(argv: list[str]) -> list[str]:
    """Redact private-key path values from argv copies used in logs."""
    out: list[str] = []
    skip_next = False
    for i, part in enumerate(argv):
        if skip_next:
            out.append("<redacted>")
            skip_next = False
            continue
        if part in {"--private-key", "-e"}:
            out.append(part)
            skip_next = True
            continue
        if part.startswith("--private-key="):
            out.append("--private-key=<redacted>")
            continue
        out.append(part)
    return out


@dataclass
class DelegatedRunResult:
    ok: bool
    status: str
    rc: int | None
    stdout: str
    stderr: str
    cmdline: str
    execution_backend: str = "ssh_delegate"

    def to_ping_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "stdout": self.stdout[:8000],
            "stderr": self.stderr[:8000],
            "reasons": [] if self.ok else [f"ssh_delegate status={self.status}"],
            "execution_backend": self.execution_backend,
            "cmdline": self.cmdline,
        }


def assert_delegate_ready(settings: Settings) -> None:
    reasons = delegate_blocking_reasons(settings)
    if reasons:
        raise RealAnsibleBlockedError(
            "; ".join(reasons), code="ssh_delegate_not_configured"
        )


def run_ssh_delegate(
    settings: Settings,
    *,
    remote_argv_parts: list[str],
    check_mode_required: bool = False,
) -> DelegatedRunResult:
    """SSH to control node and run a carefully quoted remote command."""
    assert_delegate_ready(settings)
    workdir = control_node_workdir(settings)
    remote_cmd = build_remote_shell_command(workdir, remote_argv_parts)
    if check_mode_required and "--check" not in remote_argv_parts:
        raise RealAnsibleBlockedError(
            "Internal error: delegated playbook missing --check",
            code="check_mode_required",
        )
    ssh_argv = build_ssh_argv(settings, remote_command=remote_cmd)
    timeout = control_node_timeout(settings)

    logger.info(
        "Phase 11B ssh_delegate: host=%s workdir=%s remote=%s (no secrets)",
        control_node_host(settings),
        workdir,
        " ".join(redact_for_log(remote_argv_parts)),
    )

    try:
        completed = subprocess.run(  # noqa: S603 — argv list, no shell
            ssh_argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RealAnsibleBlockedError(
            "ssh client not found on PATH", code="ssh_missing"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RealAnsibleBlockedError(
            f"ssh_delegate timed out after {timeout}s",
            code="ssh_delegate_timeout",
        ) from exc

    stdout = (completed.stdout or "")[:8000]
    stderr = (completed.stderr or "")[:8000]
    # Never echo potential secrets from remote stderr into structured logs.
    logger.info(
        "Phase 11B ssh_delegate finished: rc=%s stdout_len=%s stderr_len=%s",
        completed.returncode,
        len(stdout),
        len(stderr),
    )
    ok = completed.returncode == 0
    return DelegatedRunResult(
        ok=ok,
        status="successful" if ok else "failed",
        rc=int(completed.returncode),
        stdout=stdout,
        stderr=stderr,
        cmdline=" ".join(redact_for_log(remote_argv_parts)),
    )


def run_delegated_ping(
    settings: Settings, *, hosts: list[str], inventory_path: str
) -> dict[str, Any]:
    parts = build_remote_ping_argv(
        settings, hosts=hosts, inventory_path=inventory_path
    )
    result = run_ssh_delegate(settings, remote_argv_parts=parts)
    return result.to_ping_dict()


def run_delegated_playbook_check(
    settings: Settings,
    *,
    playbook_rel: str,
    inventory_path: str,
    limit_hosts: list[str],
) -> dict[str, Any]:
    parts = build_remote_playbook_check_argv(
        settings,
        playbook_rel=playbook_rel,
        inventory_path=inventory_path,
        limit_hosts=limit_hosts,
    )
    result = run_ssh_delegate(
        settings, remote_argv_parts=parts, check_mode_required=True
    )
    # Shape compatible with local ansible-runner check-mode result consumers.
    return {
        "ok": result.ok,
        "status": result.status,
        "rc": result.rc,
        "cmdline": result.cmdline,
        "check_mode": True,
        "playbook": playbook_rel,
        "inventory": "<remote>",
        "execution_backend": "ssh_delegate",
        "stdout": result.stdout,
        "stderr": result.stderr,
        "hosts": [
            {
                "device_name": h,
                "status": "ok" if result.ok else "failed",
                "changed": False,
                "skipped": False,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
                "return_code": result.rc,
            }
            for h in limit_hosts
        ],
    }


__all__ = [
    "DelegatedRunResult",
    "assert_delegate_ready",
    "build_remote_ping_argv",
    "build_remote_playbook_check_argv",
    "build_remote_shell_command",
    "build_ssh_argv",
    "control_node_configured",
    "control_node_host",
    "control_node_timeout",
    "control_node_user",
    "control_node_workdir",
    "delegate_available",
    "delegate_blocking_reasons",
    "redact_for_log",
    "resolve_execution_mode",
    "run_delegated_ping",
    "run_delegated_playbook_check",
    "run_ssh_delegate",
    "ssh_client_available",
]
