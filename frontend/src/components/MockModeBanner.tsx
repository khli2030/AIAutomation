"use client";

import { useEffect, useState } from "react";
import { ApiError, fetchRootMeta, getApiBase, getAdminToken } from "@/lib/api";

/**
 * Always-visible execution-mode banner on operational pages (via root layout).
 * MOCK_MODE=true (default): safe lab copy.
 * MOCK_MODE=false: stronger warning; backend gates still apply.
 */
export function MockModeBanner() {
  const [mockMode, setMockMode] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!getAdminToken()) {
        setMockMode(true);
        setError("Set a role token in Settings to connect to the API.");
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

  const isMock = mockMode !== false;
  const bannerClass = isMock ? "mock-banner" : "mock-banner real-banner";
  const tag = isMock ? "MOCK MODE" : "REAL EXECUTION MODE";
  const message = isMock
    ? "MOCK MODE: no SSH or Ansible execution is performed."
    : "REAL EXECUTION MODE: actions may affect servers. Backend gates still apply.";

  return (
    <div className={bannerClass} role="status">
      <span className="tag">{tag}</span>
      <span>{message}</span>
      <span className="muted" style={{ marginLeft: "auto", fontWeight: 500 }}>
        API {getApiBase()}
        {error ? ` · ${error}` : ""}
      </span>
    </div>
  );
}
