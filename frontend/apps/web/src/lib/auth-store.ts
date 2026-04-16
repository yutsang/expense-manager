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

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,

      login: async (email, password, mfaCode) => {
        // Use relative URL so the request goes through the Vercel proxy — cookies
        // are then set on the vercel.app domain and the middleware can read them.
        const res = await fetch("/v1/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, mfa_code: mfaCode }),
          credentials: "include",
        });
        if (res.status === 202) {
          return { requires_mfa: true };
        }
        if (!res.ok) {
          const detail = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(detail.detail ?? "Login failed");
        }
        const data = (await res.json()) as { user: User; tenant_id?: string };
        if (data.tenant_id && typeof window !== "undefined") {
          localStorage.setItem("aegis_tenant_id", data.tenant_id);
        }
        set({ user: data.user, isAuthenticated: true });
        return { requires_mfa: false };
      },

      logout: async () => {
        await fetch("/v1/auth/logout", {
          method: "POST",
          credentials: "include",
        }).catch(() => {});
        if (typeof window !== "undefined") localStorage.removeItem("aegis_tenant_id");
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
