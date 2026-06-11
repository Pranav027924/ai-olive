import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { Sidebar } from "./Sidebar";

function renderSidebar(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/sessions/:sessionId" element={<div data-testid="chat-route" />} />
          <Route path="/dashboard" element={<div data-testid="dash-route" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const sample = {
  id: "11111111-1111-1111-1111-111111111111",
  user_id: "00000000-0000-0000-0000-000000000001",
  title: "Hello world chat",
  system_prompt: null,
  provider: "anthropic" as const,
  model: "claude-opus-4-7",
  status: "active" as const,
  created_at: "2026-06-11T12:00:00Z",
  updated_at: "2026-06-11T12:00:00Z",
  messages: [],
};

beforeEach(() => {
  vi.spyOn(api, "listSessions").mockResolvedValue([sample]);
});
afterEach(() => vi.restoreAllMocks());

describe("Sidebar", () => {
  it("lists existing chats", async () => {
    renderSidebar(<Sidebar />);
    expect(await screen.findByText("Hello world chat")).toBeInTheDocument();
  });

  it("navigates to a chat when clicked", async () => {
    renderSidebar(<Sidebar />);
    await userEvent.click(await screen.findByText("Hello world chat"));
    await waitFor(() => expect(screen.getByTestId("chat-route")).toBeInTheDocument());
  });

  it("filters chats by the search box", async () => {
    renderSidebar(<Sidebar />);
    await screen.findByText("Hello world chat");
    await userEvent.type(screen.getByLabelText("search chats"), "nomatch");
    expect(screen.queryByText("Hello world chat")).not.toBeInTheDocument();
    expect(screen.getByText(/no matches/i)).toBeInTheDocument();
  });

  it("shows an empty state when there are no chats", async () => {
    vi.spyOn(api, "listSessions").mockResolvedValue([]);
    renderSidebar(<Sidebar />);
    expect(await screen.findByText(/no chats yet/i)).toBeInTheDocument();
  });
});
