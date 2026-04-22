import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "./api/client";

interface AuthState {
  loading: boolean;
  authenticated: boolean;
  actor: string | null;
  error: string | null;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [actor, setActor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const probe = useCallback(async () => {
    try {
      await api.presets();
      setAuthenticated(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setAuthenticated(false);
      } else {
        setAuthenticated(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe]);

  const login = useCallback(async (username: string, password: string) => {
    setError(null);
    try {
      const res = await api.login(username, password);
      if (res.ok) {
        setAuthenticated(true);
        setActor(res.actor ?? username);
        return true;
      }
      setError(res.error ?? "login geweigerd");
      return false;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setError("ongeldige inloggegevens");
      } else if (e instanceof Error) {
        setError(e.message);
      } else {
        setError("onbekende fout");
      }
      return false;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setAuthenticated(false);
      setActor(null);
    }
  }, []);

  const value = useMemo(
    () => ({ loading, authenticated, actor, error, login, logout }),
    [loading, authenticated, actor, error, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
