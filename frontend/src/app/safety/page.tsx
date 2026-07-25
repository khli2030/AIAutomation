"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  getAnsibleSafetyStatus,
  getLabConfigPreview,
  postConnectivityCheck,
} from "@/lib/api";
import type { AnsibleSafetyStatus, LabConfigPreview } from "@/types/api";
import { ErrorBox, SuccessBox } from "@/components/Ui";
import { useAuth } from "@/hooks/useAuth";

export default function SafetyAnsiblePage() {
  const { auth } = useAuth();
  const [status, setStatus] = useState<AnsibleSafetyStatus | null>(null);
  const [lab, setLab] = useState<LabConfigPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [hostsInput, setHostsInput] = useState("");
  const [busy, setBusy] = useState(false);

  const canOperator = Boolean(auth?.can_dry_run);
  const connectivityEnabled = Boolean(
    canOperator &&
      status?.real_execution_available &&
      lab?.connectivity_allowed,
  );

  async function refresh() {
    const [s, preview] = await Promise.all([
      getAnsibleSafetyStatus(),
      getLabConfigPreview(),
    ]);
    setStatus(s);
    setLab(preview);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
        if (!cancelled) setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.detail : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onConnectivityCheck() {
    const hosts = hostsInput
      .split(/[\s,]+/)
      .map((h) => h.trim())
      .filter(Boolean);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postConnectivityCheck(hosts);
      if (result.blocked || !result.ok) {
        setError(
          (result.reasons || []).join("; ") ||
            result.stderr ||
            "Connectivity check blocked/failed",
        );
      } else {
        setMessage("Connectivity check completed successfully (ping only).");
      }
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Safety / Ansible</h1>
        <p>
          Phase 10B lab connectivity pilot. Defaults keep{" "}
          <code>MOCK_MODE=true</code> and{" "}
          <code>REAL_ANSIBLE_ENABLED=false</code>. Connectivity check only —
          no real apply/run. Private key contents are never displayed. Excel
          Remediation and AI drafts are never executed.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />

      <div className="panel" data-testid="safety-status-panel">
        <h2>Real Ansible safety status</h2>
        {!status ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            <div className="grid-stats">
              <div className="stat">
                <div className="label">MOCK_MODE</div>
                <div className="value" data-testid="safety-mock-mode">
                  {String(status.mock_mode)}
                </div>
              </div>
              <div className="stat">
                <div className="label">REAL_ANSIBLE_ENABLED</div>
                <div className="value" data-testid="safety-real-enabled">
                  {String(status.real_ansible_enabled)}
                </div>
              </div>
              <div className="stat">
                <div className="label">CHECK_MODE_ONLY</div>
                <div className="value" data-testid="safety-check-mode-only">
                  {String(status.check_mode_only)}
                </div>
              </div>
              <div className="stat">
                <div className="label">real execution available</div>
                <div
                  className="value"
                  data-testid="safety-real-available"
                  style={{ fontSize: "1rem" }}
                >
                  {status.real_execution_available ? "YES" : "NO"}
                </div>
              </div>
            </div>
            <h3 style={{ fontSize: "0.9rem" }}>Blocked reasons</h3>
            <ul data-testid="safety-reasons">
              {(status.reasons || []).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="panel" data-testid="lab-config-preview">
        <h2>Lab config preview</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Sanitized configuration only. Paths and private key material are never
          shown.
        </p>
        {!lab ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            <div className="grid-stats">
              <div className="stat">
                <div className="label">validation status</div>
                <div className="value" data-testid="lab-validation-status">
                  {lab.validation_status}
                </div>
              </div>
              <div className="stat">
                <div className="label">inventory configured</div>
                <div className="value" data-testid="lab-inventory-configured">
                  {String(lab.inventory_path_configured)}
                </div>
              </div>
              <div className="stat">
                <div className="label">remote user configured</div>
                <div className="value" data-testid="lab-remote-user-configured">
                  {String(lab.remote_user_configured)}
                </div>
              </div>
              <div className="stat">
                <div className="label">private key configured</div>
                <div className="value" data-testid="lab-private-key-configured">
                  {String(lab.private_key_configured)}
                </div>
              </div>
              <div className="stat">
                <div className="label">timeout seconds</div>
                <div className="value" data-testid="lab-timeout-seconds">
                  {lab.timeout_seconds}
                </div>
              </div>
              <div className="stat">
                <div className="label">connectivity allowed</div>
                <div className="value">
                  {String(lab.connectivity_allowed)}
                </div>
              </div>
            </div>
            <h3 style={{ fontSize: "0.9rem" }}>Allowed hosts</h3>
            <ul data-testid="lab-allowed-hosts">
              {(lab.allowed_hosts || []).length === 0 ? (
                <li className="muted">(none)</li>
              ) : (
                lab.allowed_hosts.map((h) => <li key={h}>{h}</li>)
              )}
            </ul>
            <h3 style={{ fontSize: "0.9rem" }}>Allowed task codes</h3>
            <ul data-testid="lab-allowed-task-codes">
              {(lab.allowed_task_codes || []).length === 0 ? (
                <li className="muted">(none)</li>
              ) : (
                lab.allowed_task_codes.map((c) => (
                  <li key={c} className="mono">
                    {c}
                  </li>
                ))
              )}
            </ul>
            <h3 style={{ fontSize: "0.9rem" }}>Validation errors</h3>
            <ul data-testid="lab-validation-errors">
              {(lab.validation_errors || []).length === 0 ? (
                <li className="muted">(none)</li>
              ) : (
                lab.validation_errors.map((e) => <li key={e}>{e}</li>)
              )}
            </ul>
          </>
        )}
      </div>

      <div className="panel">
        <h2>Connectivity check (allowlisted hosts only)</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Ping only. Disabled unless safety-status allows real connectivity. Never
          runs playbooks or apply.
        </p>
        <div className="field">
          <label htmlFor="conn-hosts">Hosts (comma or space separated)</label>
          <input
            id="conn-hosts"
            data-testid="connectivity-hosts"
            value={hostsInput}
            onChange={(e) => setHostsInput(e.target.value)}
            placeholder="lab-server-01"
            disabled={!connectivityEnabled}
          />
        </div>
        <div className="btn-row">
          <button
            className="btn"
            type="button"
            data-testid="connectivity-check"
            disabled={busy || !connectivityEnabled}
            onClick={() => void onConnectivityCheck()}
          >
            Run connectivity check
          </button>
          <button
            className="btn"
            type="button"
            disabled={busy}
            onClick={() => void refresh()}
          >
            Refresh status
          </button>
        </div>
        {!connectivityEnabled ? (
          <div className="safety-note" data-testid="connectivity-disabled-note">
            Connectivity check is disabled while real execution is unavailable.
            See blocked reasons and validation errors above.
          </div>
        ) : null}
      </div>

      {/* Explicitly no real apply/run controls in Phase 10B */}
      <div className="panel" data-testid="no-real-apply-panel">
        <h2>Real apply / run</h2>
        <p className="muted" style={{ margin: 0 }}>
          Not available in Phase 10B. There is no real apply/run button and no
          production execution path on this page.
        </p>
      </div>
    </div>
  );
}
