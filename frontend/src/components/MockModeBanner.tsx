"use client";

import { useEffect, useState } from "react";
import { ApiError, fetchRootMeta, getApiBase, getAdminToken } from "@/lib/api";

export function MockModeBanner() {
  const [mockMode, setMockMode] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!getAdminToken()) {
        setMockMode(true);
        setError("Set ADMIN_TOKEN in Settings to connect to the API.");
        return;
      }
      try {
        const meta = await fetchRootMeta();
        if (!cancelled) {
          setMockMode(String(meta.mock_mode).toLowerCase() === "true");
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setMockMode(true);
          setError(
            err instanceof ApiError
              ? err.detail
              : "Could not reach API — assuming MOCK_MODE.",
          );
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const showMock = mockMode !== false;

  if (!showMock && !error) return null;

  return (
    <div className="mock-banner" role="status">
      <span className="tag">MOCK_MODE</span>
      <span>
        {showMock
          ? "Safe lab mode: no ansible-runner, ansible-playbook, subprocess, shell, or SSH."
          : "API reports MOCK_MODE=false — real Ansible is still not implemented; keep mock on."}
      </span>
      <span className="muted" style={{ marginLeft: "auto", fontWeight: 500 }}>
        API {getApiBase()}
        {error ? ` · ${error}` : ""}
      </span>
    </div>
  );
}
