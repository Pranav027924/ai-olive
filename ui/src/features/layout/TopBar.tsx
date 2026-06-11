import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/stores/auth";
import { usePrefsStore } from "@/stores/prefs";

export function TopBar(): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const theme = usePrefsStore((s) => s.theme);
  const toggleTheme = usePrefsStore((s) => s.toggleTheme);
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const [menuOpen, setMenuOpen] = useState(false);

  const initial = (user?.email?.[0] ?? "P").toUpperCase();

  return (
    <div className="flex items-center justify-end gap-2 px-4 py-2.5">
      <button
        onClick={toggleTheme}
        aria-label="toggle theme"
        className="grid h-9 w-9 place-items-center rounded-full text-muted-foreground hover:bg-accent"
      >
        {theme === "light" ? <Moon className="h-[18px] w-[18px]" /> : <Sun className="h-[18px] w-[18px]" />}
      </button>

      <div className="relative">
        <button
          onClick={() => setMenuOpen((o) => !o)}
          aria-label="account"
          className="grid h-9 w-9 place-items-center rounded-full bg-muted text-sm font-medium hover:bg-accent"
        >
          {initial}
        </button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 top-11 z-20 w-52 rounded-xl border border-border bg-card p-1 shadow-lg">
              <p className="truncate px-3 py-2 text-xs text-muted-foreground">
                {user?.email ?? "Not signed in"}
              </p>
              <button
                onClick={() => {
                  clearAuth();
                  qc.clear();
                  setMenuOpen(false);
                  navigate("/login", { replace: true });
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-accent"
              >
                <LogOut className="h-4 w-4" /> Log out
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
