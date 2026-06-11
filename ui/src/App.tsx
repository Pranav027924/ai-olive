import { Route, Routes } from "react-router-dom";

import { ChatView } from "@/features/chat/ChatView";
import { Dashboard } from "@/features/dashboard/Dashboard";
import { HomeChat } from "@/features/home/HomeChat";
import { Sidebar } from "@/features/layout/Sidebar";

export function App(): JSX.Element {
  return (
    <div className="flex h-full bg-background text-foreground">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<HomeChat />} />
          <Route path="/sessions/:sessionId" element={<ChatView />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </main>
    </div>
  );
}
