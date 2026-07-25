"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  getAnsibleSafetyStatus,
  postConnectivityCheck,
} from "@/lib/api";
import type { AnsibleSafetyStatus } from "@/types/api";
import { ErrorBox, SuccessBox } from "@/components/Ui";
import { useAuth } from "@/hooks/useAuth";

export default function SafetyAnsiblePage() {
  const { auth } = useAuth();
  const [status, setStatus] = useState<AnsibleSafetyStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [hostsInput, setHostsInput] = useState("");
  const [busy, setBusy] = useState(false);

  const canCheck = Boolean(auth?.can_dry_run);

  async function refresh() {
    const s = await getAnsibleSafetyStatus();
    setStatus(s);
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
        setMessage("Connectivity check completed successfully.");
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
          Phase 10A pilot readiness. Defaults keep{" "}
          <code>MOCK_MODE=true</code> and{" "}
          <code>REAL_ANSIBLE_ENABLED=false</code>. Real apply/run is not
          enabled. Excel Remediation and AI drafts are never executed.
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
                <div className="label">allowed hosts</div>
                <div className="value">{status.allowed_hosts_count}</div>
              </div>
              <div className="stat">
                <div className="label">allowed task codes</div>
                <div className="value">{status.allowed_task_codes_count}</div>
              </div>
              <div className="stat">
                <div className="label">inventory configured</div>
                <div className="value">
                  {String(status.inventory_configured)}
                </div>
              </div>
              <div className="stat">
                <div className="label">private key configured</div>
                <div className="value">
                  {String(status.private_key_configured)}
                </div>
              </div>
              <div className="stat">
                <div className="label">remote user configured</div>
                <div className="value">
                  {String(status.remote_user_configured)}
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
            <h3 style={{ fontSize: "0.9rem" }}>Reasons / blockers</h3>
            <ul data-testid="safety-reasons">
              {(status.reasons || []).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="panel">
        <h2>Connectivity check (allowlisted hosts only)</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Blocked when real Ansible is disabled. Never runs playbooks or apply.
        </p>
        <div className="field">
          <label htmlFor="conn-hosts">Hosts (comma or space separated)</label>
          <input
            id="conn-hosts"
            data-testid="connectivity-hosts"
            value={hostsInput}
            onChange={(e) => setHostsInput(e.target.value)}
            placeholder="e2e-linux-01"
          />
        </div>
        <div className="btn-row">
          <button
            className="btn"
            type="button"
            data-testid="connectivity-check"
            disabled={busy || !canCheck}
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
      </div>
    </div>
  );
}
