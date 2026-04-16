import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';

interface AuthState {
  isAuthenticated: boolean;
  userId: string | null;
  tenantId: string | null;
  setAuth: (userId: string, tenantId: string) => void;
  clearAuth: () => void;
  checkAuth: () => Promise<boolean>;
}

export const useAuthStore = create<AuthState>((set) => ({
  isAuthenticated: false,
  userId: null,
  tenantId: null,
  setAuth: (userId, tenantId) => set({ isAuthenticated: true, userId, tenantId }),
  clearAuth: () => set({ isAuthenticated: false, userId: null, tenantId: null }),
  checkAuth: async () => {
    const token = await SecureStore.getItemAsync('aegis_access');
    if (token) {
      set({ isAuthenticated: true });
      return true;
    }
    return false;
  },
}));
