import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { SessionList } from "./SessionList";

function renderWithProviders(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/sessions/:sessionId" element={<div data-testid="chat-route" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const sample = {
  id: "11111111-1111-1111-1111-111111111111",
  user_id: "00000000-0000-0000-0000-000000000001",
  title: "Sample",
  system_prompt: null,
  provider: "anthropic" as const,
  model: "claude-opus-4-7",
  status: "active" as const,
  created_at: "2026-06-09T12:00:00Z",
  updated_at: "2026-06-09T12:00:00Z",
  messages: [],
};

beforeEach(() => {
  vi.spyOn(api, "listSessions").mockResolvedValue([sample]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SessionList", () => {
  it("renders the existing sessions", async () => {
    renderWithProviders(<SessionList />);
    expect(await screen.findByText("Sample")).toBeInTheDocument();
    expect(screen.getByText(/anthropic.*claude-opus-4-7/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no sessions", async () => {
    vi.spyOn(api, "listSessions").mockResolvedValue([]);
    renderWithProviders(<SessionList />);
    expect(await screen.findByText(/no sessions yet/i)).toBeInTheDocument();
  });

  it("creates a session and navigates to its chat route", async () => {
    const created = { ...sample, id: "22222222-2222-2222-2222-222222222222", title: "New" };
    const createSpy = vi.spyOn(api, "createSession").mockResolvedValue(created);

    renderWithProviders(<SessionList />);
    await screen.findByRole("button", { name: /create/i });

    await userEvent.type(screen.getByPlaceholderText("Untitled"), "New");
    await userEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
    expect(createSpy.mock.calls[0][0]).toMatchObject({ provider: "anthropic", title: "New" });
    await waitFor(() => expect(screen.getByTestId("chat-route")).toBeInTheDocument());
  });

  it("surfaces a failure state when listSessions rejects", async () => {
    vi.spyOn(api, "listSessions").mockRejectedValue(new Error("boom"));
    renderWithProviders(<SessionList />);
    expect(await screen.findByText(/failed to load sessions/i)).toBeInTheDocument();
  });
});
