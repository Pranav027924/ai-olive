import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { HomeChat } from "./HomeChat";

function renderHome() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<HomeChat />} />
          <Route path="/sessions/:sessionId" element={<div data-testid="chat-route" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const created = {
  id: "22222222-2222-2222-2222-222222222222",
  user_id: "00000000-0000-0000-0000-000000000001",
  title: "Hi there",
  system_prompt: null,
  provider: "anthropic" as const,
  model: "claude-opus-4-7",
  status: "active" as const,
  created_at: "2026-06-11T12:00:00Z",
  updated_at: "2026-06-11T12:00:00Z",
  messages: [],
};

beforeEach(() => {
  vi.spyOn(api, "createSession").mockResolvedValue(created);
  vi.spyOn(api, "sendUserMessage").mockResolvedValue({} as never);
});
afterEach(() => vi.restoreAllMocks());

describe("HomeChat", () => {
  it("renders the greeting and composer", () => {
    renderHome();
    expect(screen.getByText(/ready when you are/i)).toBeInTheDocument();
    expect(screen.getByLabelText("message-input")).toBeInTheDocument();
  });

  it("creates a session + posts the first message, then navigates to the chat", async () => {
    renderHome();
    await userEvent.type(screen.getByLabelText("message-input"), "Hi there");
    await userEvent.click(screen.getByLabelText("send"));

    await waitFor(() => expect(api.createSession).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.createSession).mock.calls[0][0]).toMatchObject({ provider: "anthropic" });
    expect(api.sendUserMessage).toHaveBeenCalledWith(created.id, "Hi there");
    await waitFor(() => expect(screen.getByTestId("chat-route")).toBeInTheDocument());
  });

  it("respects the selected provider", async () => {
    renderHome();
    await userEvent.selectOptions(screen.getByLabelText("provider"), "openai");
    await userEvent.type(screen.getByLabelText("message-input"), "hello");
    await userEvent.click(screen.getByLabelText("send"));
    await waitFor(() => expect(api.createSession).toHaveBeenCalled());
    expect(vi.mocked(api.createSession).mock.calls[0][0]).toMatchObject({ provider: "openai" });
  });
});
