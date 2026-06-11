import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutGrid, MoreHorizontal, Plus, Search, Settings, Trash2 } from "lucide-react";
import { useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";

import { deleteSession, listSessions } from "@/api/client";
import { Logo } from "@/components/Logo";
import { cn } from "@/lib/cn";
import { useAuthStore } from "@/stores/auth";

export function Sidebar(): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { sessionId } = useParams();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });
  const [query, setQuery] = useState("");
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const user = useAuthStore((s) => s.user);

  const remove = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      setMenuFor(null);
      if (id === sessionId) navigate("/");
    },
  });

  const rows = (sessions.data ?? [])
    .filter((s) => s.status !== "deleted")
    .filter((s) => (s.title || "Untitled").toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-sidebar text-sm">
      {/* Brand */}
      <div className="flex items-center justify-between px-3 py-3">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 rounded-lg px-1.5 py-1 font-semibold hover:bg-accent"
        >
          <Logo className="h-7 w-7" />
          AI-Olive
        </button>
        <button
          onClick={() => navigate("/")}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent"
          aria-label="new chat"
          title="New chat"
        >
          <Plus className="h-[18px] w-[18px]" />
        </button>
      </div>

      {/* New chat (prominent, filled) */}
      <div className="px-2">
        <button
          onClick={() => navigate("/")}
          className="flex w-full items-center gap-2.5 rounded-xl bg-primary px-3 py-2.5 font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-[18px] w-[18px]" /> New chat
        </button>
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            cn(
              "mt-1 flex w-full items-center gap-2.5 rounded-lg px-3 py-2 hover:bg-accent",
              isActive && "bg-accent font-medium",
            )
          }
        >
          <LayoutGrid className="h-[18px] w-[18px]" /> Dashboard
        </NavLink>
      </div>

      {/* Search */}
      <div className="px-2 py-2">
        <div className="flex items-center gap-2 rounded-lg border border-transparent bg-background/60 px-3 py-2 text-muted-foreground focus-within:border-border">
          <Search className="h-4 w-4" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats"
            aria-label="search chats"
            className="w-full bg-transparent text-foreground placeholder:text-muted-foreground focus:outline-none"
          />
        </div>
      </div>

      {/* Recents */}
      <div className="mt-1 flex-1 overflow-y-auto px-2 pb-3 scrollbar-thin">
        <p className="px-3 pb-1 pt-2 text-xs font-medium text-muted-foreground">Chats</p>
        {sessions.isPending ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">Loading…</p>
        ) : sessions.isError ? (
          <p className="px-3 py-2 text-xs text-destructive">Failed to load chats.</p>
        ) : rows.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            {query ? "No matches." : "No chats yet."}
          </p>
        ) : (
          <ul data-testid="chat-list">
            {rows.map((s) => (
              <li key={s.id} className="group relative">
                <button
                  onClick={() => navigate(`/sessions/${s.id}`)}
                  title={s.title || "Untitled"}
                  className={cn(
                    "block w-full truncate rounded-lg py-2 pl-3 pr-8 text-left hover:bg-accent",
                    s.id === sessionId && "bg-accent font-medium",
                  )}
                >
                  {s.title || "Untitled"}
                </button>
                <button
                  onClick={() => setMenuFor(menuFor === s.id ? null : s.id)}
                  aria-label="chat menu"
                  className={cn(
                    "absolute right-1 top-1.5 grid h-7 w-7 place-items-center rounded-md text-muted-foreground",
                    "opacity-0 hover:bg-border group-hover:opacity-100",
                    menuFor === s.id && "opacity-100",
                  )}
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>
                {menuFor === s.id && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setMenuFor(null)} />
                    <div className="absolute right-1 top-9 z-20 w-40 rounded-xl border border-border bg-card p-1 shadow-lg">
                      <button
                        onClick={() => remove.mutate(s.id)}
                        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-destructive hover:bg-accent"
                      >
                        <Trash2 className="h-4 w-4" /> Delete chat
                      </button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-border px-2 py-2">
        <div className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-accent">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-muted text-xs font-medium">
            {(user?.email?.[0] ?? "P").toUpperCase()}
          </span>
          <span className="flex-1 truncate text-xs text-muted-foreground">
            {user?.email ?? "dev@local"}
          </span>
          <Settings className="h-4 w-4 text-muted-foreground" />
        </div>
      </div>
    </aside>
  );
}
