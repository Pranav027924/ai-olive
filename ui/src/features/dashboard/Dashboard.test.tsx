import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/api/client";
import { Dashboard } from "./Dashboard";

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Dashboard />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "getLatency").mockResolvedValue({ window: "1h", p50: 120, p95: 300, p99: 900 });
  vi.spyOn(api, "getThroughput").mockResolvedValue({ window: "1h", request_count: 42 });
  vi.spyOn(api, "getErrorRate").mockResolvedValue({ window: "1h", error_rate: 0.125 });
  vi.spyOn(api, "getCost").mockResolvedValue({
    window: "1h",
    breakdown: [{ provider: "openai", cost_usd: 1.23 }],
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Dashboard", () => {
  it("renders the four headline stats once the queries settle", async () => {
    renderDashboard();
    expect(await screen.findByText("42")).toBeInTheDocument(); // request count
    expect(await screen.findByText("12.50%")).toBeInTheDocument(); // error rate
    expect(await screen.findByText("120 ms")).toBeInTheDocument(); // p50
    expect(await screen.findByText("900 ms")).toBeInTheDocument(); // p99
  });

  it("renders the latency + cost chart containers", async () => {
    renderDashboard();
    await screen.findByText("42");
    expect(screen.getByTestId("latency-chart")).toBeInTheDocument();
    expect(screen.getByTestId("cost-chart")).toBeInTheDocument();
  });
});
