"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { api, setToken, clearToken, ApiError } from "@/lib/api";

export type WorkspaceMembership = {
  workspace_id: string;
  workspace_name: string;
  role: string;
};

export type User = {
  id: string;
  name: string;
  email: string;
  username: string;
  role: "admin" | "employee";
  department_id: string;
  department_name: string;
  permissions: string[];
  workspace_memberships: WorkspaceMembership[];
};

type AuthState = {
  user: User | null;
  loading: boolean;
  /**
   * Sign in with either a username or an email. The string is sent as
   * `username` to the backend; the backend resolves it against both
   * `employees.username` and `employees.email` so users keep working
   * even if they remember their old email instead of the new handle.
   */
  login: (identifier: string, password: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
  hasPermission: (perm: string) => boolean;
  /** Check if user can perform resource:action (matches :own_dept or :all) */
  canAccess: (resource: string, action: string) => boolean;
  /** Get workspace role for a specific workspace */
  getWorkspaceRole: (workspaceId: string) => string | null;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api<{
        id: string;
        name: string;
        email: string;
        username: string;
        role: "admin" | "employee";
        department_id: string;
        department_name: string;
        permissions: string[];
        workspace_memberships: WorkspaceMembership[];
      }>("/api/auth/me");
      setUser(data);
    } catch (err) {
      setUser(null);
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        clearToken();
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Migrate token from old key (arkon_token) to new key (cmd_support_token)
    if (typeof window !== "undefined") {
      const oldToken = localStorage.getItem("arkon_token");
      const newToken = localStorage.getItem("cmd_support_token");
      if (oldToken && !newToken) {
        localStorage.setItem("cmd_support_token", oldToken);
        localStorage.removeItem("arkon_token");
      }
    }

    const token = localStorage.getItem("cmd_support_token");
    if (token) {
      refresh();
    } else {
      setLoading(false);
    }
  }, [refresh]);

  const login = async (identifier: string, password: string): Promise<User> => {
    const data = await api<{ access_token: string; user: User }>(
      "/api/auth/login",
      {
        method: "POST",
        // Send as `username` — the backend accepts either username or email
        // through that field. The legacy `email` field is still recognised
        // server-side but the frontend has migrated to the new contract.
        body: { username: identifier, password },
      }
    );
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    clearToken();
    setUser(null);
  };

  const hasPermission = useCallback(
    (perm: string) => {
      if (!user) return false;
      if (user.role === "admin") return true;
      return user.permissions?.includes(perm) ?? false;
    },
    [user]
  );

  const canAccess = useCallback(
    (resource: string, action: string) => {
      if (!user) return false;
      if (user.role === "admin") return true;
      const all = `${resource}:${action}:all`;
      const own = `${resource}:${action}:own_dept`;
      return (
        (user.permissions?.includes(all) ?? false) ||
        (user.permissions?.includes(own) ?? false)
      );
    },
    [user]
  );

  const getWorkspaceRole = useCallback(
    (workspaceId: string): string | null => {
      if (!user) return null;
      if (user.role === "admin") return "admin";
      const membership = user.workspace_memberships?.find(
        (m) => m.workspace_id === workspaceId
      );
      return membership?.role ?? null;
    },
    [user]
  );

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, refresh, hasPermission, canAccess, getWorkspaceRole }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
