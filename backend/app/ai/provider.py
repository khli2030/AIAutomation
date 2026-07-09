"""AI Remediation Analyzer interface.

MVP: mock provider only. External providers must be explicitly configured.
AI output is never executed automatically.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from app.config import get_settings

# Prompt template stored in code for later provider wiring (Phase 4).
AI_ANALYZER_PROMPT_TEMPLATE = """
You are a Linux compliance remediation analyzer.

Analyze the following compliance finding and convert it into a safe structured remediation proposal.

Important rules:
* Do not execute anything.
* Do not generate destructive commands.
* Do not assume missing values.
* Do not use raw shell commands unless absolutely necessary.
* Prefer Ansible built-in modules such as lineinfile, copy, file, mount, service, and command for validation only.
* Any change to SSH, SELinux, fstab, permissions, or system security files must require backup, validation, dry-run, and human approval.
* If the remediation is unclear, return NEEDS_REVIEW.
* If the remediation cannot be safely automated, return UNSUPPORTED_CONTROL.
* Return JSON only.

Input fields:
* Qualys Control ID: {{qualys_control_id}}
* Source Check ID: {{source_check_id}}
* Control Description: {{control_description}}
* RATIONALE: {{rationale}}
* Remediation: {{remediation}}
* Expected Configuration: {{expected_configuration}}

Return this JSON structure:
{
  "classification": {
    "task_code": "",
    "confidence": 0.0,
    "status": "READY_FOR_REVIEW | NEEDS_REVIEW | UNSUPPORTED_CONTROL",
    "reason": ""
  },
  "remediation_plan": {
    "title": "",
    "risk_level": "low | medium | high | critical",
    "target_os": "linux",
    "target_file": "",
    "setting_name": "",
    "expected_value": "",
    "ansible_module": "",
    "requires_backup": true,
    "requires_service_reload": false,
    "service_name": "",
    "requires_reboot": false
  },
  "safety": {
    "possible_impact": "",
    "validation_command": "",
    "rollback_strategy": "",
    "approval_required": true
  },
  "ansible_draft": {
    "playbook_yaml": ""
  }
}
""".strip()

# Heuristic patterns for richer mock drafts (still never executed).
_MOCK_HINTS: list[tuple[str, dict[str, Any]]] = [
    (
        r"permitrootlogin",
        {
            "task_code": "SSH_DISABLE_ROOT_LOGIN",
            "confidence": 0.92,
            "target_file": "/etc/ssh/sshd_config",
            "setting_name": "PermitRootLogin",
            "expected_value": "no",
            "ansible_module": "ansible.builtin.lineinfile",
            "risk_level": "high",
            "title": "Disable SSH root login",
        },
    ),
    (
        r"x11forwarding",
        {
            "task_code": "SSH_DISABLE_X11_FORWARDING",
            "confidence": 0.88,
            "target_file": "/etc/ssh/sshd_config",
            "setting_name": "X11Forwarding",
            "expected_value": "no",
            "ansible_module": "ansible.builtin.lineinfile",
            "risk_level": "medium",
            "title": "Disable SSH X11 forwarding",
        },
    ),
    (
        r"selinux|setenforce",
        {
            "task_code": "SET_SELINUX_MODE",
            "confidence": 0.85,
            "target_file": "/etc/selinux/config",
            "setting_name": "SELINUX",
            "expected_value": "enforcing",
            "ansible_module": "ansible.builtin.lineinfile",
            "risk_level": "critical",
            "title": "Set SELinux mode",
        },
    ),
    (
        r"fstab|/tmp.*nodev|/dev/shm|noexec|nodev",
        {
            "task_code": "NEEDS_REVIEW",
            "confidence": 0.55,
            "target_file": "/etc/fstab",
            "setting_name": "mount_options",
            "expected_value": "",
            "ansible_module": "ansible.posix.mount",
            "risk_level": "critical",
            "title": "Filesystem mount option change",
        },
    ),
    (
        r"chmod|permissions|/var/log",
        {
            "task_code": "SET_VAR_LOG_PERMISSIONS",
            "confidence": 0.8,
            "target_file": "/var/log",
            "setting_name": "mode",
            "expected_value": "0750",
            "ansible_module": "ansible.builtin.file",
            "risk_level": "high",
            "title": "Set directory permissions",
        },
    ),
]


def _combined_finding_text(finding: dict[str, Any]) -> str:
    parts = [
        finding.get("qualys_control_id"),
        finding.get("source_check_id"),
        finding.get("control_description"),
        finding.get("rationale"),
        finding.get("remediation"),
        finding.get("expected_configuration"),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def _draft_playbook(
    *,
    task_code: str,
    target_file: str,
    setting_name: str,
    expected_value: str,
    ansible_module: str,
) -> str:
    """Return draft YAML text only — never written to disk or executed by AI path."""
    if not target_file and not setting_name:
        return (
            "---\n"
            "# DRAFT ONLY — not executable via AI Analyzer\n"
            "# Human review + convert-to-catalog required before any use.\n"
            f"# suggested_task_code: {task_code}\n"
        )
    module = ansible_module or "ansible.builtin.lineinfile"
    return (
        "---\n"
        "# DRAFT ONLY — AI-generated; never execute directly\n"
        f"- name: Draft remediation for {task_code}\n"
        "  hosts: all\n"
        "  become: true\n"
        "  tasks:\n"
        f"    - name: Apply {setting_name or 'setting'} (draft)\n"
        f"      {module}:\n"
        f"        path: {target_file or '/etc/unknown'}\n"
        + (
            f"        regexp: '^{setting_name}\\s+'\n"
            f"        line: '{setting_name} {expected_value}'\n"
            if setting_name and expected_value and "lineinfile" in module
            else f"        # expected: {expected_value}\n"
        )
        + "\n# END DRAFT — requires human approval and catalog conversion\n"
    )


class AIProvider(ABC):
    """Provider interface — implementations must return structured dict only."""

    @abstractmethod
    def analyze(self, finding: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MockAIProvider(AIProvider):
    """Deterministic mock provider — structured JSON only; never calls external APIs."""

    def analyze(self, finding: dict[str, Any]) -> dict[str, Any]:
        text = _combined_finding_text(finding)
        hint: dict[str, Any] | None = None
        for pattern, payload in _MOCK_HINTS:
            if re.search(pattern, text):
                hint = payload
                break

        if hint is None:
            task_code = "NEEDS_REVIEW"
            confidence = 0.0
            risk_level = "high"
            target_file = ""
            setting_name = ""
            expected_value = ""
            ansible_module = ""
            title = "Needs human review"
            reason = "Mock AI provider — no clear remediation pattern matched."
            classification_status = "NEEDS_REVIEW"
        else:
            task_code = str(hint["task_code"])
            confidence = float(hint["confidence"])
            risk_level = str(hint["risk_level"])
            target_file = str(hint["target_file"])
            setting_name = str(hint["setting_name"])
            expected_value = str(hint["expected_value"])
            ansible_module = str(hint["ansible_module"])
            title = str(hint["title"])
            reason = "Mock AI heuristic match — human review still required."
            classification_status = (
                "NEEDS_REVIEW" if task_code == "NEEDS_REVIEW" else "READY_FOR_REVIEW"
            )

        playbook = _draft_playbook(
            task_code=task_code,
            target_file=target_file,
            setting_name=setting_name,
            expected_value=expected_value,
            ansible_module=ansible_module,
        )

        return {
            "classification": {
                "task_code": task_code,
                "confidence": confidence,
                "status": classification_status,
                "reason": reason,
            },
            "remediation_plan": {
                "title": title,
                "risk_level": risk_level,
                "target_os": "linux",
                "target_file": target_file,
                "setting_name": setting_name,
                "expected_value": expected_value,
                "ansible_module": ansible_module,
                "requires_backup": True,
                "requires_service_reload": "ssh" in target_file.lower() if target_file else False,
                "service_name": "sshd" if "ssh" in target_file.lower() else "",
                "requires_reboot": False,
            },
            "safety": {
                "possible_impact": (
                    "May affect remote access, security policy, or filesystem mounts. "
                    "Human approval required before any catalog conversion."
                ),
                "validation_command": "",
                "rollback_strategy": (
                    "Restore backed-up configuration file; do not apply until reviewed."
                ),
                "approval_required": True,
            },
            "ansible_draft": {
                "playbook_yaml": playbook,
            },
            "meta": {
                "provider": "mock",
                "prompt_template_version": "1",
                "input_keys": sorted(finding.keys()),
                "executable": False,
            },
        }


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    # MVP: always mock. External OpenAI/Claude wiring is intentionally not implemented.
    if not settings.ai_enabled or settings.ai_provider == "mock":
        return MockAIProvider()
    return MockAIProvider()
