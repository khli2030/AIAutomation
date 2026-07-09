"""AI Remediation Analyzer interface.

MVP: mock provider only. External providers must be explicitly configured.
AI output is never executed automatically.
"""

from __future__ import annotations

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


class AIProvider(ABC):
    """Provider interface — implementations must return structured dict only."""

    @abstractmethod
    def analyze(self, finding: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class MockAIProvider(AIProvider):
    """Deterministic placeholder used when AI_ENABLED is false or provider=mock."""

    def analyze(self, finding: dict[str, Any]) -> dict[str, Any]:
        return {
            "classification": {
                "task_code": "NEEDS_REVIEW",
                "confidence": 0.0,
                "status": "NEEDS_REVIEW",
                "reason": "Mock AI provider — no external model configured.",
            },
            "remediation_plan": {
                "title": "Needs human review",
                "risk_level": "high",
                "target_os": "linux",
                "target_file": "",
                "setting_name": "",
                "expected_value": "",
                "ansible_module": "",
                "requires_backup": True,
                "requires_service_reload": False,
                "service_name": "",
                "requires_reboot": False,
            },
            "safety": {
                "possible_impact": "Unknown — human review required.",
                "validation_command": "",
                "rollback_strategy": "Do not apply until reviewed.",
                "approval_required": True,
            },
            "ansible_draft": {
                "playbook_yaml": "",
            },
            "meta": {
                "provider": "mock",
                "prompt_template_version": "1",
                "input_keys": sorted(finding.keys()),
            },
        }


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if not settings.ai_enabled or settings.ai_provider == "mock":
        return MockAIProvider()
    # Future: optional on-prem / internal LLM endpoint only (never required).
    # Do not wire public SaaS AI cloud APIs into this platform.
    return MockAIProvider()
