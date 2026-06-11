import { Route, Routes } from "react-router-dom";

import { LoginPage } from "@/features/auth/LoginPage";
import { ChatView } from "@/features/chat/ChatView";
import { Dashboard } from "@/features/dashboard/Dashboard";
import { HomeChat } from "@/features/home/HomeChat";
import { Shell } from "@/features/layout/Shell";

export function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Shell />}>
        <Route path="/" element={<HomeChat />} />
        <Route path="/sessions/:sessionId" element={<ChatView />} />
        <Route path="/dashboard" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}
