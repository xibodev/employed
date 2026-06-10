"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { apiFetch } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  isAdmin: boolean;
  isEmailVerified: boolean;
}

interface AuthActions {
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  loginWithOAuth: (provider: string) => void;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

type AuthContextValue = AuthState & AuthActions;
type AppUser = AuthUser & {
  isAdmin?: boolean;
  /** Snake_case field as returned by the API (/users/me, /auth/login). */
  email_verified?: boolean;
  /** Legacy camelCase variant kept for backward compatibility. */
  emailVerified?: boolean;
  deletionRequestedAt?: string;
  deletionScheduledFor?: string;
  emails?: Array<{ address?: string; verified?: boolean }>;
};

type AuthResponse = {
  token?: string;
  accessToken?: string;
  access_token?: string;
  refreshToken?: string;
  refresh_token?: string;
  user?: AppUser;
};

const TOKEN_KEY = "employed_token";
const REFRESH_TOKEN_KEY = "employed_refresh_token";
const TOKEN_COOKIE = "employed_token";
const ADMIN_COOKIE = "employed_is_admin";
const REFRESH_BUFFER_MS = 60_000;
const FALLBACK_REFRESH_MS = 15 * 60 * 1000;

const AuthContext = createContext<AuthContextValue | null>(null);

function getStoredToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  return window.localStorage.getItem(TOKEN_KEY);
}

function getStoredRefreshToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

function clearStoredToken() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

function setCookie(name: string, value: string, expiresAt?: number) {
  if (typeof document === "undefined") {
    return;
  }

  const parts = [`${name}=${encodeURIComponent(value)}`, "Path=/", "SameSite=Lax"];
  if (expiresAt) {
    parts.push(`Expires=${new Date(expiresAt).toUTCString()}`);
  }
  document.cookie = parts.join("; ");
}

function clearCookie(name: string) {
  if (typeof document === "undefined") {
    return;
  }

  document.cookie = `${name}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax`;
}

function normalizeBase64(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const remainder = normalized.length % 4;
  if (remainder === 0) {
    return normalized;
  }
  return `${normalized}${"=".repeat(4 - remainder)}`;
}

function parseJwtExpiry(token: string | null) {
  if (!token || typeof window === "undefined") {
    return null;
  }

  const segments = token.split(".");
  if (segments.length !== 3) {
    return null;
  }

  try {
    const payload = JSON.parse(window.atob(normalizeBase64(segments[1])));
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function isAdminUser(user: AppUser | null) {
  if (!user) {
    return false;
  }

  if (user.isAdmin) {
    return true;
  }

  return Array.isArray(user.roles) && user.roles.includes("admin");
}

function isVerifiedUser(user: AppUser | null) {
  if (!user) {
    return false;
  }

  // EMP-029: the API returns snake_case email_verified; reading only the
  // camelCase variant showed every verified user as "Pending verification".
  if (typeof user.email_verified === "boolean") {
    return user.email_verified;
  }

  if (typeof user.emailVerified === "boolean") {
    return user.emailVerified;
  }

  return !!user.emails?.some((email) => email.verified);
}

function persistToken(token: string, refreshToken?: string) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(TOKEN_KEY, token);
  if (refreshToken) {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
  const expiresAt = parseJwtExpiry(token) ?? Date.now() + 7 * 24 * 60 * 60 * 1000;
  setCookie(TOKEN_COOKIE, token, expiresAt);
}

async function fetchMe(token: string) {
  return apiFetch<AppUser>("/users/me", {
    token,
    cache: "no-store",
  });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    isLoading: true,
    isAdmin: false,
    isEmailVerified: false,
  });
  const refreshTimeoutRef = useRef<number | null>(null);

  const clearRefreshTimer = useCallback(() => {
    if (typeof window !== "undefined" && refreshTimeoutRef.current) {
      window.clearTimeout(refreshTimeoutRef.current);
      refreshTimeoutRef.current = null;
    }
  }, []);

  const applyAuth = useCallback((user: AppUser | null, token: string | null, refreshTokenValue?: string) => {
    if (token) {
      persistToken(token, refreshTokenValue);
    }

    if (user) {
      setCookie(ADMIN_COOKIE, isAdminUser(user) ? "1" : "0", parseJwtExpiry(token) ?? undefined);
    } else {
      clearCookie(ADMIN_COOKIE);
    }

    setState({
      user,
      token,
      isLoading: false,
      isAdmin: isAdminUser(user),
      isEmailVerified: isVerifiedUser(user),
    });
  }, []);

  const logout = useCallback(() => {
    clearRefreshTimer();
    // Capture the refresh token BEFORE clearing local state so the server can
    // revoke its JTI in Redis. Best-effort; ignore failures.
    const refreshTokenToRevoke = getStoredRefreshToken();
    clearStoredToken();
    clearCookie(TOKEN_COOKIE);
    clearCookie(ADMIN_COOKIE);
    setState({
      user: null,
      token: null,
      isLoading: false,
      isAdmin: false,
      isEmailVerified: false,
    });
    void apiFetch<void>("/auth/logout", {
      method: "POST",
      body: refreshTokenToRevoke ? { refresh_token: refreshTokenToRevoke } : undefined,
    }).catch(() => undefined);
  }, [clearRefreshTimer]);

  const refreshToken = useCallback(async () => {
    const storedRefreshToken = getStoredRefreshToken();
    if (!storedRefreshToken) {
      logout();
      return;
    }

    try {
      const payload = await apiFetch<AuthResponse>("/auth/refresh", {
        method: "POST",
        body: { refresh_token: storedRefreshToken },
        cache: "no-store",
      });
      const nextToken = payload.token ?? payload.accessToken ?? payload.access_token ?? (getStoredToken() ?? "");
      const nextRefresh = payload.refreshToken ?? payload.refresh_token ?? storedRefreshToken;
      const user = payload.user ?? (await fetchMe(nextToken));
      applyAuth(user, nextToken, nextRefresh);
    } catch {
      logout();
    }
  }, [applyAuth, logout]);

  const scheduleRefresh = useCallback(
    (token: string | null) => {
      clearRefreshTimer();
      if (!token || typeof window === "undefined") {
        return;
      }

      const expiresAt = parseJwtExpiry(token);
      const delay = expiresAt ? Math.max(expiresAt - Date.now() - REFRESH_BUFFER_MS, 5_000) : FALLBACK_REFRESH_MS;
      refreshTimeoutRef.current = window.setTimeout(() => {
        void refreshToken();
      }, delay);
    },
    [clearRefreshTimer, refreshToken],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const payload = await apiFetch<AuthResponse>("/auth/login", {
        method: "POST",
        body: { email, password },
        cache: "no-store",
      });
      const token = payload.token ?? payload.accessToken ?? payload.access_token;
      if (!token) {
        throw new Error("No access token returned by login.");
      }

      const refreshTokenValue = payload.refreshToken ?? payload.refresh_token;
      const user = payload.user ?? (await fetchMe(token));
      applyAuth(user, token, refreshTokenValue ?? undefined);
    },
    [applyAuth],
  );

  const register = useCallback(async (email: string, password: string, name: string) => {
    await apiFetch<void>("/auth/register", {
      method: "POST",
      body: { email, password, name },
      cache: "no-store",
    });
  }, []);

  const loginWithOAuth = useCallback((provider: string) => {
    if (typeof window === "undefined") {
      return;
    }

    const destination = new URL(`/auth/oauth/${provider}`, window.location.origin);
    const redirect = `${window.location.pathname}${window.location.search}`;
    destination.searchParams.set("redirect", redirect);
    window.location.assign(destination.toString());
  }, []);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      const token = getStoredToken();
      if (!token) {
        if (!cancelled) {
          setState((current) => ({ ...current, isLoading: false }));
        }
        return;
      }

      try {
        const user = await fetchMe(token);
        if (!cancelled) {
          applyAuth(user, token);
        }
      } catch {
        if (!cancelled) {
          logout();
        }
      }
    };

    void bootstrap();

    return () => {
      cancelled = true;
      clearRefreshTimer();
    };
  }, [applyAuth, clearRefreshTimer, logout]);

  useEffect(() => {
    if (!state.token) {
      clearRefreshTimer();
      return;
    }

    scheduleRefresh(state.token);
  }, [clearRefreshTimer, scheduleRefresh, state.token]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const handleStorage = async (event: StorageEvent) => {
      if (event.key !== TOKEN_KEY) {
        return;
      }

      if (!event.newValue) {
        logout();
        return;
      }

      try {
        const user = await fetchMe(event.newValue);
        applyAuth(user, event.newValue);
      } catch {
        logout();
      }
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [applyAuth, logout]);

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      login,
      register,
      loginWithOAuth,
      logout,
      refreshToken,
    }),
    [login, logout, refreshToken, register, state, loginWithOAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
