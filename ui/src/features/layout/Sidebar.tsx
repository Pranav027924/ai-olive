import { useQuery } from "@tanstack/react-query";
import { BarChart3, PenSquare, Search } from "lucide-react";
import { useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";

import { listSessions } from "@/api/client";
import { cn } from "@/lib/cn";

export function Sidebar(): JSX.Element {
  const navigate = useNavigate();
  const { sessionId } = useParams();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });
  const [query, setQuery] = useState("");

  const rows = (sessions.data ?? []).filter((s) =>
    (s.title || "Untitled").toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-sidebar text-sm">
      {/* Brand + new chat */}
      <div className="flex items-center justify-between px-3 py-3">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 rounded-lg px-2 py-1 font-semibold hover:bg-accent"
        >
          <span className="grid h-6 w-6 place-items-center rounded-full bg-primary text-primary-foreground text-xs">
            O
          </span>
          AI-OLive
        </button>
        <button
          onClick={() => navigate("/")}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent"
          aria-label="new chat"
          title="New chat"
        >
          <PenSquare className="h-[18px] w-[18px]" />
        </button>
      </div>

      {/* Primary actions */}
      <div className="px-2">
        <button
          onClick={() => navigate("/")}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 font-medium hover:bg-accent"
        >
          <PenSquare className="h-[18px] w-[18px]" /> New chat
        </button>
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            cn(
              "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 hover:bg-accent",
              isActive && "bg-accent font-medium",
            )
          }
        >
          <BarChart3 className="h-[18px] w-[18px]" /> Dashboard
        </NavLink>
      </div>

      {/* Search */}
      <div className="px-2 py-2">
        <div className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-muted-foreground">
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
        <p className="px-2.5 pb-1 pt-2 text-xs font-medium text-muted-foreground">Chats</p>
        {sessions.isPending ? (
          <p className="px-2.5 py-2 text-xs text-muted-foreground">Loading…</p>
        ) : sessions.isError ? (
          <p className="px-2.5 py-2 text-xs text-destructive">Failed to load chats.</p>
        ) : rows.length === 0 ? (
          <p className="px-2.5 py-2 text-xs text-muted-foreground">
            {query ? "No matches." : "No chats yet."}
          </p>
        ) : (
          <ul data-testid="chat-list">
            {rows.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => navigate(`/sessions/${s.id}`)}
                  title={s.title || "Untitled"}
                  className={cn(
                    "block w-full truncate rounded-lg px-2.5 py-2 text-left hover:bg-accent",
                    s.id === sessionId && "bg-accent font-medium",
                  )}
                >
                  {s.title || "Untitled"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-border px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-muted text-xs font-medium">
            PB
          </span>
          <span className="text-xs text-muted-foreground">dev@local</span>
        </div>
      </div>
    </aside>
  );
}
