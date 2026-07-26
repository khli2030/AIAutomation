"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  getAnsibleSafetyStatus,
  getLabConfigPreview,
  getPilotReadiness,
  postConnectivityCheck,
} from "@/lib/api";
import type {
  AnsibleSafetyStatus,
  LabConfigPreview,
  PilotReadiness,
} from "@/types/api";
import { ErrorBox, SuccessBox } from "@/components/Ui";
import { useAuth } from "@/hooks/useAuth";

export default function SafetyAnsiblePage() {
  const { auth } = useAuth();
  const [status, setStatus] = useState<AnsibleSafetyStatus | null>(null);
  const [lab, setLab] = useState<LabConfigPreview | null>(null);
  const [pilot, setPilot] = useState<PilotReadiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [hostsInput, setHostsInput] = useState("");
  const [busy, setBusy] = useState(false);

  const canOperator = Boolean(auth?.can_dry_run);
  const maxHosts =
    pilot?.max_hosts_per_run ?? status?.max_hosts_per_run ?? lab?.max_hosts_per_run ?? 1;
  const pilotReady = Boolean(pilot?.ready ?? lab?.pilot_ready);
  const connectivityEnabled = Boolean(
    canOperator &&
      status?.real_execution_available &&
      lab?.connectivity_allowed &&
      (status?.pilot_mode ?? pilot?.pilot_mode),
  );

  const parsedHosts = useMemo(
    () =>
      hostsInput
        .split(/[\s,]+/)
        .map((h) => h.trim())
        .filter(Boolean),
    [hostsInput],
  );
  const tooManyHosts = parsedHosts.length > maxHosts;

  async function refresh() {
    const [s, preview, readiness] = await Promise.all([
      getAnsibleSafetyStatus(),
      getLabConfigPreview(),
      getPilotReadiness(),
    ]);
    setStatus(s);
    setLab(preview);
    setPilot(readiness);
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
    if (tooManyHosts) {
      setError(
        `Single-host pilot allows at most ${maxHosts} host(s) per run. Remove extra hosts before checking.`,
      );
      setMessage(null);
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await postConnectivityCheck(parsedHosts);
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
          Phase 10C single-host lab pilot. Defaults keep{" "}
          <code>MOCK_MODE=true</code>,{" "}
          <code>REAL_ANSIBLE_ENABLED=false</code>, and{" "}
          <code>REAL_ANSIBLE_PILOT_MODE=false</code>. Connectivity and real
          dry-run are check-mode / ping only — no real apply/run. Private key
          contents are never displayed. Excel Remediation and AI drafts are never
          executed.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={message} />

      <div className="panel" data-testid="pilot-readiness-panel">
        <h2>Pilot Readiness</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Single-host lab pilot gate. Connectivity and real dry-run stay blocked
          until every check below is green.
        </p>
        {!pilot ? (
          <p className="muted">Loading…</p>
        ) : (
          <>
            <div className="grid-stats">
              <div className="stat">
                <div className="label">pilot_ready</div>
                <div className="value" data-testid="pilot-ready-badge">
                  {pilotReady ? "true" : "false"}
                </div>
              </div>
              <div className="stat">
                <div className="label">max_hosts_per_run</div>
                <div className="value" data-testid="max-hosts-per-run">
                  {String(maxHosts)}
                </div>
              </div>
              <div className="stat">
                <div className="label">pilot_mode</div>
                <div className="value">{String(pilot.pilot_mode)}</div>
              </div>
              <div className="stat">
                <div className="label">check_mode_only</div>
                <div className="value">{String(pilot.check_mode_only)}</div>
              </div>
            </div>

            <div
              className="safety-note"
              data-testid="max-host-warning"
              style={{ marginTop: "0.75rem" }}
            >
              Single-host pilot enforces max_hosts_per_run={maxHosts}.
              Connectivity checks and real dry-runs that target more hosts are
              rejected. Never use production or critical hosts.
            </div>

            <h3 style={{ fontSize: "0.9rem" }}>Blocked reasons</h3>
            <ul data-testid="pilot-blocked-reasons">
              {(pilot.errors || []).length === 0 ? (
                <li className="muted">(none)</li>
              ) : (
                pilot.errors.map((r) => <li key={r}>{r}</li>)
              )}
            </ul>

            <h3 style={{ fontSize: "0.9rem" }}>Warnings</h3>
            <ul data-testid="pilot-warnings">
              {(pilot.warnings || []).length === 0 ? (
                <li className="muted">(none)</li>
              ) : (
                pilot.warnings.map((w) => <li key={w}>{w}</li>)
              )}
            </ul>
          </>
        )}
      </div>

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
                <div className="label">PILOT_MODE</div>
                <div className="value" data-testid="safety-pilot-mode">
                  {String(status.pilot_mode ?? false)}
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
              <div className="stat">
                <div className="label">single_host_pilot_qualified</div>
                <div
                  className="value"
                  data-testid="safety-pilot-qualified"
                  style={{ fontSize: "1rem" }}
                >
                  {status.single_host_pilot_qualified ? "YES" : "NO"}
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
                <div className="label">pilot_ready</div>
                <div className="value" data-testid="lab-pilot-ready">
                  {String(lab.pilot_ready ?? false)}
                </div>
              </div>
              <div className="stat">
                <div className="label">max_hosts_per_run</div>
                <div className="value">{String(lab.max_hosts_per_run ?? 1)}</div>
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
            {(lab.pilot_readiness_errors || []).length > 0 ? (
              <>
                <h3 style={{ fontSize: "0.9rem" }}>Pilot readiness errors</h3>
                <ul data-testid="lab-pilot-readiness-errors">
                  {lab.pilot_readiness_errors!.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </>
            ) : null}
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
          Ping only. At most {maxHosts} host(s) per run. Disabled unless pilot
          readiness allows real connectivity. Never runs playbooks or apply.
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
        {tooManyHosts ? (
          <div className="safety-note" data-testid="connectivity-host-limit">
            Too many hosts ({parsedHosts.length}). Max allowed per run:{" "}
            {maxHosts}.
          </div>
        ) : null}
        <div className="btn-row">
          <button
            className="btn"
            type="button"
            data-testid="connectivity-check"
            disabled={busy || !connectivityEnabled || tooManyHosts}
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
            Connectivity check is disabled while pilot readiness / real execution
            is unavailable. See Pilot Readiness blocked reasons above.
          </div>
        ) : null}
      </div>

      {/* Explicitly no real apply/run controls in Phase 10C */}
      <div className="panel" data-testid="no-real-apply-panel">
        <h2>Real apply / run</h2>
        <p className="muted" style={{ margin: 0 }}>
          Not available in Phase 10C. There is no real apply/run button and no
          production execution path on this page.
        </p>
      </div>
    </div>
  );
}
