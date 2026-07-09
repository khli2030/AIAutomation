"use client";

import { useEffect, useState } from "react";
import {
  DEFAULT_API_BASE,
  getAdminToken,
  getApiBase,
  setAdminToken,
} from "@/lib/api";
import { SuccessBox } from "@/components/Ui";

export default function SettingsPage() {
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    setToken(getAdminToken());
  }, []);

  function onSave(e: React.FormEvent) {
    e.preventDefault();
    setAdminToken(token);
    setSaved("Token stored in sessionStorage for this browser tab only.");
  }

  function onClear() {
    setAdminToken("");
    setToken("");
    setSaved("Token cleared from sessionStorage.");
  }

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
        <p>
          Configure API access. Never commit <code>ADMIN_TOKEN</code>. Prefer
          pasting it here into sessionStorage for local lab use.
        </p>
      </div>
      <SuccessBox message={saved} />
      <div className="panel">
        <div className="field">
          <label>Backend URL (from NEXT_PUBLIC_API_URL)</label>
          <input value={getApiBase()} readOnly />
          <span className="muted">
            Default {DEFAULT_API_BASE}. Change via env, not this form.
          </span>
        </div>
        <form onSubmit={onSave}>
          <div className="field">
            <label htmlFor="token">ADMIN_TOKEN</label>
            <input
              id="token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste token from .env — never commit"
            />
          </div>
          <div className="btn-row">
            <button className="btn primary" type="submit">
              Save to sessionStorage
            </button>
            <button className="btn danger" type="button" onClick={onClear}>
              Clear
            </button>
          </div>
        </form>
        <div className="safety-note">
          Optional lab-only override: <code>NEXT_PUBLIC_ADMIN_TOKEN</code> in{" "}
          <code>.env.local</code> (gitignored). Do not put secrets in committed
          files. This UI never edits Ansible playbooks.
        </div>
      </div>
    </div>
  );
}
