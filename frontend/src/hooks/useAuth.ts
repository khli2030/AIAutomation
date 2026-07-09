"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, fetchAuthMe, getAdminToken, type AuthMe } from "@/lib/api";

export type UseAuthResult = {
  auth: AuthMe | null;
  loading: boolean;
  error: string | null;
  hasToken: boolean;
  refresh: () => Promise<void>;
};

/**
 * Resolve current role from /auth/me using the sessionStorage role token.
 * MVP-only — not production authentication.
 */
export function useAuth(): UseAuthResult {
  const [auth, setAuth] = useState<AuthMe | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasToken, setHasToken] = useState(false);

  const refresh = useCallback(async () => {
    const token = getAdminToken();
    setHasToken(Boolean(token));
    if (!token) {
      setAuth(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const me = await fetchAuthMe();
      setAuth(me);
      setError(null);
    } catch (err) {
      setAuth(null);
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { auth, loading, error, hasToken, refresh };
}
