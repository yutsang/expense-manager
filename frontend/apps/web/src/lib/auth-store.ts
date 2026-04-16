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
        const data = (await res.json()) as {
          access_token: string;
          user: User;
          tenant_ids?: string[];
          tenant_id?: string;
        };
        if (typeof window !== "undefined") {
          if (data.access_token) localStorage.setItem("aegis_token", data.access_token);
          const tid = data.tenant_id ?? data.tenant_ids?.[0];
          if (tid) localStorage.setItem("aegis_tenant_id", tid);
          // Set a JS-visible cookie so the Next.js middleware can detect auth state
          document.cookie = "aegis_client=1; path=/; max-age=2592000; SameSite=Lax"; // 30 days
        }
        set({ user: data.user, isAuthenticated: true });
        return { requires_mfa: false };
      },

      logout: async () => {
        await fetch("/v1/auth/logout", {
          method: "POST",
          credentials: "include",
        }).catch(() => {});
        if (typeof window !== "undefined") {
          localStorage.removeItem("aegis_tenant_id");
          localStorage.removeItem("aegis_token");
          document.cookie = "aegis_client=; path=/; max-age=0";
        }
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
