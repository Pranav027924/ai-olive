import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import { LoginPage } from "./LoginPage";

function renderLogin() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div data-testid="home-route" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const token = {
  access_token: "jwt-token",
  token_type: "bearer",
  user: { id: "u1", email: "me@example.com" },
};

beforeEach(() => {
  useAuthStore.setState({ token: null, user: null, unauthorized: false });
});
afterEach(() => vi.restoreAllMocks());

describe("LoginPage", () => {
  it("logs in, stores the token, and navigates home", async () => {
    const spy = vi.spyOn(api, "login").mockResolvedValue(token);
    renderLogin();

    await userEvent.type(screen.getByLabelText("email"), "me@example.com");
    await userEvent.type(screen.getByLabelText("password"), "correct-horse");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledWith("me@example.com", "correct-horse"));
    await waitFor(() => expect(screen.getByTestId("home-route")).toBeInTheDocument());
    expect(useAuthStore.getState().token).toBe("jwt-token");
  });

  it("shows an error on bad credentials", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new Error("401"));
    renderLogin();
    await userEvent.type(screen.getByLabelText("email"), "me@example.com");
    await userEvent.type(screen.getByLabelText("password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });

  it("can switch to register mode", async () => {
    renderLogin();
    await userEvent.click(screen.getByRole("button", { name: /create an account/i }));
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });
});
