"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  DEFAULT_API_BASE,
  fetchAuthMe,
  getAdminToken,
  getApiBase,
  setAdminToken,
  type AuthMe,
} from "@/lib/api";
import { ErrorBox, SuccessBox } from "@/components/Ui";

export default function SettingsPage() {
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [me, setMe] = useState<AuthMe | null>(null);
  const [busy, setBusy] = useState(false);

  async function detectRole(currentToken: string) {
    if (!currentToken.trim()) {
      setMe(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const auth = await fetchAuthMe();
      setMe(auth);
    } catch (err) {
      setMe(null);
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const existing = getAdminToken();
    setToken(existing);
    if (existing) void detectRole(existing);
  }, []);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setAdminToken(token);
    setSaved(
      "Role token stored in sessionStorage for this browser tab only (MVP).",
    );
    await detectRole(token);
  }

  function onClear() {
    setAdminToken("");
    setToken("");
    setMe(null);
    setError(null);
    setSaved("Token cleared from sessionStorage.");
  }

  return (
    <div>
      <div className="page-header">
        <h1>Settings / Login</h1>
        <p>
          Paste a role token from the environment (
          <code>VIEWER_TOKEN</code>, <code>OPERATOR_TOKEN</code>,{" "}
          <code>APPROVER_TOKEN</code>, or <code>ADMIN_TOKEN</code>). Never
          hardcode or commit tokens. This is{" "}
          <strong>MVP-only</strong> — not production authentication.
        </p>
      </div>
      <ErrorBox message={error} />
      <SuccessBox message={saved} />
      <div className="panel">
        <div className="field">
          <label>Backend URL (from NEXT_PUBLIC_API_URL)</label>
          <input value={getApiBase()} readOnly />
          <span className="muted">
            Default {DEFAULT_API_BASE}. Change via env, not this form.
          </span>
        </div>
        <form onSubmit={(e) => void onSave(e)}>
          <div className="field">
            <label htmlFor="token">Role token</label>
            <input
              id="token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste VIEWER/OPERATOR/APPROVER/ADMIN token — never commit"
            />
          </div>
          <div className="btn-row">
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Checking…" : "Save & detect role"}
            </button>
            <button className="btn danger" type="button" onClick={onClear}>
              Clear
            </button>
          </div>
        </form>
        {me ? (
          <div className="grid-stats" style={{ marginTop: "1rem" }}>
            <div className="stat">
              <div className="label">current role</div>
              <div className="value" style={{ fontSize: "1.1rem" }}>
                {me.role}
              </div>
            </div>
            <div className="stat">
              <div className="label">actor</div>
              <div className="value" style={{ fontSize: "0.95rem" }}>
                {me.actor}
              </div>
            </div>
            <div className="stat">
              <div className="label">token env</div>
              <div className="value" style={{ fontSize: "0.95rem" }}>
                {me.token_name}
              </div>
            </div>
          </div>
        ) : (
          <p className="muted" style={{ marginTop: "1rem" }}>
            No valid role detected yet. Save a token to call{" "}
            <code>/auth/me</code>.
          </p>
        )}
        <div className="safety-note">
          {me?.mvp_auth_warning ||
            "MVP-only: sessionStorage / optional gitignored NEXT_PUBLIC_ADMIN_TOKEN is a shared lab token, not production auth. Do not put secrets in committed files."}{" "}
          Tokens are never hardcoded in the UI. This console never edits Ansible
          playbooks.
        </div>
      </div>
    </div>
  );
}
