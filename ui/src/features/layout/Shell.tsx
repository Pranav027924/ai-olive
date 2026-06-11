import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "@/stores/auth";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function Shell(): JSX.Element {
  const unauthorized = useAuthStore((s) => s.unauthorized);
  if (unauthorized) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-full bg-background text-foreground">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <TopBar />
        <div className="min-h-0 flex-1">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
