import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getCost, getErrorRate, getLatency, getThroughput } from "@/api/client";
import type { WindowKey } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Dropdown } from "@/components/ui/dropdown";
import { usePrefsStore } from "@/stores/prefs";

const WINDOWS = [
  { value: "1h" as const, label: "Last hour" },
  { value: "24h" as const, label: "Last 24 hours" },
  { value: "7d" as const, label: "Last 7 days" },
];

const LATENCY_COLOR = "#10b981"; // emerald
const PROVIDER_COLORS: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  gemini: "#4285f4",
  deepseek: "#7c3aed",
};

export function Dashboard(): JSX.Element {
  const theme = usePrefsStore((s) => s.theme);
  const axis = theme === "dark" ? "#a1a1aa" : "#6b7280";
  const grid = theme === "dark" ? "#27272a" : "#ececec";
  const cursorFill = theme === "dark" ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)";

  const [window, setWindow] = useState<WindowKey>("24h");
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
        { name: "p50", value: Math.round(latency.data.p50) },
        { name: "p95", value: Math.round(latency.data.p95) },
        { name: "p99", value: Math.round(latency.data.p99) },
      ]
    : [];
  const costData = (cost.data?.breakdown ?? []).map((c) => ({
    provider: c.provider,
    cost_usd: c.cost_usd,
  }));
  const totalCost = costData.reduce((s, c) => s + c.cost_usd, 0);

  return (
    <div className="h-full space-y-6 overflow-y-auto px-6 py-6 scrollbar-thin">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Inference metrics across your chats.</p>
        </div>
        <Dropdown<WindowKey>
          aria-label="time window"
          value={window}
          onChange={setWindow}
          align="right"
          options={WINDOWS}
        />
      </header>

      {/* Headline stats */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Requests"
          value={throughput.data?.request_count}
          pending={throughput.isPending}
          accent="text-foreground"
        />
        <Stat
          label="Error rate"
          value={
            errorRate.data !== undefined
              ? `${(errorRate.data.error_rate * 100).toFixed(2)}%`
              : undefined
          }
          pending={errorRate.isPending}
          accent={
            errorRate.data && errorRate.data.error_rate > 0 ? "text-destructive" : "text-foreground"
          }
        />
        <Stat
          label="p50 latency"
          value={latency.data ? `${Math.round(latency.data.p50)} ms` : undefined}
          pending={latency.isPending}
        />
        <Stat
          label="p99 latency"
          value={latency.data ? `${Math.round(latency.data.p99)} ms` : undefined}
          pending={latency.isPending}
        />
      </section>

      {/* Charts */}
      <section className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Latency percentiles" subtitle="milliseconds, lower is better">
          <div className="h-64" data-testid="latency-chart">
            {latency.isPending ? (
              <Empty>Loading…</Empty>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={latencyData} margin={{ top: 16, right: 8, left: -8, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={grid} />
                  <XAxis dataKey="name" stroke={axis} fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis
                    stroke={axis}
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    tickFormatter={(v) => `${v}ms`}
                  />
                  <Tooltip
                    cursor={{ fill: cursorFill }}
                    content={<ChartTooltip unit="ms" />}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]} fill={LATENCY_COLOR} maxBarSize={72}>
                    <LabelList
                      dataKey="value"
                      position="top"
                      fontSize={12}
                      fill={axis}
                      formatter={(v: number) => `${v}ms`}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </ChartCard>

        <ChartCard title="Cost by provider" subtitle={`total ${usd(totalCost)}`}>
          <div className="h-64" data-testid="cost-chart">
            {cost.isPending ? (
              <Empty>Loading…</Empty>
            ) : costData.length === 0 ? (
              <Empty>No spend in this window.</Empty>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={costData}
                  layout="vertical"
                  margin={{ top: 4, right: 56, left: 8, bottom: 0 }}
                >
                  <CartesianGrid horizontal={false} stroke={grid} />
                  <XAxis
                    type="number"
                    stroke={axis}
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={usd}
                  />
                  <YAxis
                    type="category"
                    dataKey="provider"
                    stroke={axis}
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    width={76}
                  />
                  <Tooltip cursor={{ fill: cursorFill }} content={<ChartTooltip unit="$" />} />
                  <Bar dataKey="cost_usd" radius={[0, 6, 6, 0]} maxBarSize={28}>
                    {costData.map((d) => (
                      <Cell key={d.provider} fill={PROVIDER_COLORS[d.provider] ?? LATENCY_COLOR} />
                    ))}
                    <LabelList
                      dataKey="cost_usd"
                      position="right"
                      fontSize={12}
                      fill={axis}
                      formatter={usd}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </ChartCard>
      </section>
    </div>
  );
}

function usd(v: number): string {
  if (v >= 1) return `$${v.toFixed(2)}`;
  if (v >= 0.01) return `$${v.toFixed(3)}`;
  return `$${v.toFixed(5)}`;
}

function Stat({
  label,
  value,
  pending,
  accent = "text-foreground",
}: {
  label: string;
  value: string | number | undefined;
  pending: boolean;
  accent?: string;
}): JSX.Element {
  return (
    <Card className="transition-colors hover:border-foreground/20">
      <CardContent className="p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`mt-1 text-2xl font-semibold tabular-nums ${accent}`}>
          {pending ? "…" : (value ?? "—")}
        </p>
      </CardContent>
    </Card>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-3">
          <p className="text-sm font-medium">{title}</p>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function Empty({ children }: { children: React.ReactNode }): JSX.Element {
  return <div className="grid h-full place-items-center text-sm text-muted-foreground">{children}</div>;
}

interface TooltipProps {
  active?: boolean;
  label?: string;
  unit?: string;
  payload?: { value: number; payload: { provider?: string } }[];
}

function ChartTooltip({ active, label, unit, payload }: TooltipProps): JSX.Element | null {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  const name = label ?? payload[0].payload.provider ?? "";
  const text = unit === "$" ? usd(v) : `${v} ${unit ?? ""}`.trim();
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-sm shadow-md">
      <p className="font-medium capitalize">{name}</p>
      <p className="text-muted-foreground tabular-nums">{text}</p>
    </div>
  );
}
