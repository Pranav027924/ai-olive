import { Link, NavLink, Route, Routes } from "react-router-dom";

import { SessionListPage } from "@/routes/SessionListPage";
import { ChatPage } from "@/routes/ChatPage";
import { DashboardPage } from "@/routes/DashboardPage";

export function App(): JSX.Element {
  return (
    <div className="grid h-full grid-rows-[auto_1fr]">
      <header className="border-b border-border bg-card px-4 py-2 flex items-center gap-4">
        <Link to="/" className="font-semibold">
          AI-OLive
        </Link>
        <nav className="flex gap-3 text-sm">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
            }
          >
            Sessions
          </NavLink>
          <NavLink
            to="/dashboard"
            className={({ isActive }) =>
              isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
            }
          >
            Dashboard
          </NavLink>
        </nav>
      </header>
      <main className="overflow-hidden">
        <Routes>
          <Route path="/" element={<SessionListPage />} />
          <Route path="/sessions/:sessionId" element={<ChatPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
    </div>
  );
}
