"use client";

import { useAuth } from "@/hooks/useAuth";

/** Compact current-role indicator for the sidebar (MVP token auth). */
export function RoleBadge() {
  const { auth, loading, hasToken, error } = useAuth();

  if (loading) {
    return <p className="muted" style={{ fontSize: "0.75rem" }}>Detecting role…</p>;
  }
  if (!hasToken) {
    return (
      <p className="muted" style={{ fontSize: "0.75rem" }}>
        No token — open Settings
      </p>
    );
  }
  if (error || !auth) {
    return (
      <p className="muted" style={{ fontSize: "0.75rem" }}>
        Token invalid — check Settings
      </p>
    );
  }
  return (
    <p style={{ fontSize: "0.75rem", margin: 0 }}>
      Role: <strong>{auth.role}</strong>
      <br />
      <span className="muted">{auth.actor}</span>
    </p>
  );
}
