/**
 * Auth state store (Zustand).
 * Tokens are stored in httpOnly cookies set by the API; this store only
 * tracks client-side auth state for UI purposes.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface User {
  id: string;
  email: string;
  display_name: string;
  current_tenant_id: string | null;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  login: (
    email: string,
    password: string,
    mfaCode?: string
  ) => Promise<{ requires_mfa: boolean }>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,

      login: async (email, password, mfaCode) => {
        const res = await fetch(`${API_BASE}/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, mfa_code: mfaCode }),
          credentials: "include",
        });
        if (res.status === 202) {
          // Server asks for MFA
          return { requires_mfa: true };
        }
        if (!res.ok) {
          const detail = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(detail.detail ?? "Login failed");
        }
        const data = (await res.json()) as { user: User };
        set({ user: data.user, isAuthenticated: true });
        return { requires_mfa: false };
      },

      logout: async () => {
        await fetch(`${API_BASE}/v1/auth/logout`, {
          method: "POST",
          credentials: "include",
        }).catch(() => {});
        set({ user: null, isAuthenticated: false });
      },

      setUser: (user) => set({ user, isAuthenticated: true }),
    }),
    {
      name: "aegis-auth",
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
);
