import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getCost, getErrorRate, getLatency, getThroughput } from "@/api/client";
import type { WindowKey } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const WINDOWS: { value: WindowKey; label: string }[] = [
  { value: "1h", label: "Last hour" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
];

export function Dashboard(): JSX.Element {
  const [window, setWindow] = useState<WindowKey>("1h");
  const [latency, throughput, errorRate, cost] = useQueries({
    queries: [
      { queryKey: ["dash", "latency", window], queryFn: () => getLatency(window) },
      { queryKey: ["dash", "throughput", window], queryFn: () => getThroughput(window) },
      { queryKey: ["dash", "error-rate", window], queryFn: () => getErrorRate(window) },
      { queryKey: ["dash", "cost", window], queryFn: () => getCost(window) },
    ],
  });

  const latencyData = latency.data
    ? [
        { name: "p50", value: latency.data.p50 },
        { name: "p95", value: latency.data.p95 },
        { name: "p99", value: latency.data.p99 },
      ]
    : [];
  const costData = cost.data?.breakdown ?? [];

  return (
    <div className="container py-6 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Dashboard</h1>
        <select
          value={window}
          onChange={(e) => setWindow(e.target.value as WindowKey)}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
          aria-label="time window"
        >
          {WINDOWS.map((w) => (
            <option key={w.value} value={w.value}>
              {w.label}
            </option>
          ))}
        </select>
      </header>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Requests" value={throughput.data?.request_count} pending={throughput.isPending} />
        <Stat
          label="Error rate"
          value={
            errorRate.data !== undefined ? `${(errorRate.data.error_rate * 100).toFixed(2)}%` : undefined
          }
          pending={errorRate.isPending}
        />
        <Stat label="p50 latency" value={latency.data ? `${Math.round(latency.data.p50)} ms` : undefined} pending={latency.isPending} />
        <Stat label="p99 latency" value={latency.data ? `${Math.round(latency.data.p99)} ms` : undefined} pending={latency.isPending} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Latency percentiles (ms)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64" data-testid="latency-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={latencyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="value" fill="hsl(var(--primary))" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Cost by provider (USD)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64" data-testid="cost-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={costData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="provider" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="cost_usd" fill="hsl(var(--primary))" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  pending,
}: {
  label: string;
  value: string | number | undefined;
  pending: boolean;
}): JSX.Element {
  return (
    <Card>
      <CardContent>
        <p className="text-xs uppercase text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold">{pending ? "…" : (value ?? "—")}</p>
      </CardContent>
    </Card>
  );
}
