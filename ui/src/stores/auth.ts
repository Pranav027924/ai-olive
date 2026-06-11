import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: string;
  email: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  /** Set when a request 401s so the app can redirect to /login. */
  unauthorized: boolean;
  setAuth: (token: string, user: AuthUser) => void;
  clearAuth: () => void;
  setUnauthorized: (v: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      unauthorized: false,
      setAuth: (token, user) => set({ token, user, unauthorized: false }),
      clearAuth: () => set({ token: null, user: null }),
      setUnauthorized: (v) => set({ unauthorized: v }),
    }),
    { name: "olive-auth", partialize: (s) => ({ token: s.token, user: s.user }) },
  ),
);
