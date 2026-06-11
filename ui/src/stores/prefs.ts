import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Provider } from "@/api/types";

type Theme = "light" | "dark";

interface PrefsState {
  provider: Provider;
  theme: Theme;
  setProvider: (p: Provider) => void;
  toggleTheme: () => void;
}

function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
}

export const usePrefsStore = create<PrefsState>()(
  persist(
    (set, get) => ({
      provider: "anthropic",
      theme: "light",
      setProvider: (provider) => set({ provider }),
      toggleTheme: () => {
        const theme = get().theme === "light" ? "dark" : "light";
        applyTheme(theme);
        set({ theme });
      },
    }),
    {
      name: "olive-prefs",
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.theme);
      },
    },
  ),
);
