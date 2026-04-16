"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { getAiCostSummary, type CostSummary } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

// Input: $0.27 / 1M tokens → $0.00000027 per token
// Output: $1.10 / 1M tokens → $0.0000011 per token
const INPUT_COST_PER_TOKEN = 0.00000027;
const OUTPUT_COST_PER_TOKEN = 0.0000011;

function estimateCost(inputTokens: number, outputTokens: number): string {
  const cost = inputTokens * INPUT_COST_PER_TOKEN + outputTokens * OUTPUT_COST_PER_TOKEN;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(cost);
}

function fmtNum(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

interface StatCardProps {
  label: string;
  data: CostSummary["today"];
}

function StatCard({ label, data }: StatCardProps) {
  const cost = estimateCost(data.input_tokens, data.output_tokens);
  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <p className="text-sm font-medium text-muted-foreground mb-4">{label}</p>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Input tokens</p>
          <p className="text-xl font-semibold tabular-nums">{fmtNum(data.input_tokens)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Output tokens</p>
          <p className="text-xl font-semibold tabular-nums">{fmtNum(data.output_tokens)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Messages</p>
          <p className="text-xl font-semibold tabular-nums">{fmtNum(data.messages)}</p>
        </div>
      </div>
      <div className="mt-3 border-t pt-3">
        <p className="text-xs text-muted-foreground">
          Est. cost: <span className="font-semibold text-foreground">{cost}</span>
        </p>
      </div>
    </div>
  );
}

interface ChartEntry {
  date: string;
  input_tokens: number;
  output_tokens: number;
  est_cost: number;
}

function UsageChart({ byDay }: { byDay: CostSummary["by_day"] }) {
  const data: ChartEntry[] = byDay.map((d) => ({
    date: d.date.slice(5), // MM-DD
    input_tokens: d.input_tokens,
    output_tokens: d.output_tokens,
    est_cost: parseFloat(
      (d.input_tokens * INPUT_COST_PER_TOKEN + d.output_tokens * OUTPUT_COST_PER_TOKEN).toFixed(4)
    ),
  }));

  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <h2 className="mb-1 text-sm font-semibold">Token usage — last 30 days</h2>
      <p className="mb-4 text-xs text-muted-foreground">Input tokens (blue) + Output tokens (purple)</p>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
          <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              ((value: unknown, name: unknown) => [
                typeof value === "number" ? fmtNum(value) : String(value ?? ""),
                name === "input_tokens" ? "Input tokens" : "Output tokens",
              ]) as any // recharts Formatter type is overly strict
            }
          />
          <Legend
            formatter={(value: string) =>
              value === "input_tokens" ? "Input tokens" : "Output tokens"
            }
          />
          <Bar dataKey="input_tokens" fill="#3b82f6" stackId="tokens" name="input_tokens" />
          <Bar dataKey="output_tokens" fill="#8b5cf6" stackId="tokens" name="output_tokens" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function CostByDayTable({ byDay }: { byDay: CostSummary["by_day"] }) {
  const rows = [...byDay].reverse().slice(0, 10);
  return (
    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
      <div className="border-b bg-muted/20 px-4 py-3">
        <h2 className="text-sm font-semibold">Recent daily breakdown</h2>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40">
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Date</th>
            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Input tokens</th>
            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Output tokens</th>
            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Est. cost</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((d) => (
            <tr key={d.date} className="hover:bg-muted/20 transition-colors">
              <td className="px-4 py-3 font-mono text-xs">{d.date}</td>
              <td className="px-4 py-3 text-right tabular-nums">{fmtNum(d.input_tokens)}</td>
              <td className="px-4 py-3 text-right tabular-nums">{fmtNum(d.output_tokens)}</td>
              <td className="px-4 py-3 text-right font-mono tabular-nums">
                {estimateCost(d.input_tokens, d.output_tokens)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AiCostPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["ai-cost-summary"],
    queryFn: getAiCostSummary,
  });

  return (
    <>
      <PageHeader title="AI Usage & Cost" subtitle="Token consumption and estimated cost for Claude AI" />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {isLoading && (
          <div className="text-sm text-muted-foreground">Loading usage data…</div>
        )}
        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error instanceof Error ? error.message : String(error)}
          </div>
        )}
        {data && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <StatCard label="Today" data={data.today} />
              <StatCard label="This Month" data={data.this_month} />
            </div>
            <UsageChart byDay={data.by_day} />
            <CostByDayTable byDay={data.by_day} />
          </>
        )}
      </div>
    </>
  );
}
