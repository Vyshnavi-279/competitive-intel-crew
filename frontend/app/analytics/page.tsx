"use client";

/**
 * PHASE 4 ADDITION — Usage Analytics page (/analytics)
 *
 * A NEW standalone page — does NOT modify the existing dashboard or any
 * other page.  Shows two charts using the existing navy/teal/amber colour
 * palette already used across the app:
 *
 *   1. Bar chart   — runs per user (submitted_by breakdown)
 *   2. Line chart  — runs per day over the last 30 days
 *
 * Data is fetched from GET /api/analytics/usage (Phase 4 backend endpoint).
 */

import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";
import { BarChart2, TrendingUp, RefreshCw } from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface UserStat {
  submitted_by: string;
  run_count: number;
  avg_duration_seconds: number;
}

interface DayCount {
  date: string;
  run_count: number;
}

interface UsageData {
  by_user: UserStat[];
  daily_trend: DayCount[];
}

// ---------------------------------------------------------------------------
// Colour tokens (match the app's clay palette)
// ---------------------------------------------------------------------------
const TEAL   = "#93B6C4";
const AMBER  = "#E8C4A2";
const GREEN  = "#A9C6AE";
const TEXT   = "#2E2A22";
const MUTED  = "#6B6358";
const BG     = "#F7F2E9";
const GRID   = "#D6CEC4";

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------
function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { value: number; name: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-xl px-3 py-2 text-[12px]"
      style={{
        background: BG,
        boxShadow: "3px 3px 8px rgba(74,68,56,0.2), -2px -2px 6px rgba(255,255,255,0.7)",
        color: TEXT,
        fontFamily: "var(--font-poppins), Poppins, sans-serif",
      }}
    >
      <p className="font-semibold mb-0.5">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: MUTED }}>
          {p.name}: <strong style={{ color: TEXT }}>{p.value}</strong>
        </p>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section card wrapper
// ---------------------------------------------------------------------------
function Card({ title, icon: Icon, children }: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <div
      className="rounded-[20px] p-6"
      style={{
        background: "linear-gradient(145deg, #F7F2E9, #EDE4D4)",
        boxShadow: "5px 5px 14px rgba(74,68,56,0.15), -4px -4px 10px rgba(255,255,255,0.75)",
      }}
    >
      <div className="flex items-center gap-2 mb-5">
        <span
          className="flex items-center justify-center w-8 h-8 rounded-xl shrink-0"
          style={{ background: `${TEAL}22`, boxShadow: `2px 2px 6px rgba(74,68,56,0.15), -1px -1px 4px rgba(255,255,255,0.7)` }}
        >
          <Icon size={16} strokeWidth={2} color={MUTED} />
        </span>
        <p
          className="text-[14px] font-semibold"
          style={{ color: TEXT, fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
        >
          {title}
        </p>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------
export default function AnalyticsPage() {
  const [data, setData]       = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function load(showRefresh = false) {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://competitive-intel-crew-2.onrender.com";
      const res = await fetch(`${API_BASE}/api/analytics/usage`);
      if (!res.ok) throw new Error(`API ${res.status}`);
      const json: UsageData = await res.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analytics");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => { load(); }, []);

  const hasUsers = (data?.by_user?.length ?? 0) > 0;
  const hasTrend = (data?.daily_trend?.length ?? 0) > 0;

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p
            className="text-[11px] font-bold tracking-widest uppercase mb-1"
            style={{ color: "#9A9086", fontFamily: "var(--font-poppins), Poppins, sans-serif", letterSpacing: "0.1em" }}
          >
            Analytics
          </p>
          <h1
            className="text-3xl font-semibold"
            style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: TEXT }}
          >
            Usage Analytics
          </h1>
          <p className="mt-1 text-sm" style={{ color: TEXT }}>
            Run counts by analyst and daily trend over the last 30 days.
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing || loading}
          className="flex items-center gap-2 px-4 py-2 text-[12px] font-semibold rounded-full hover:brightness-95 active:scale-95 transition-all disabled:opacity-50"
          style={{
            background: "#F7F2E9",
            color: TEXT,
            boxShadow: "3px 3px 8px rgba(74,68,56,0.18), -2px -2px 6px rgba(255,255,255,0.7)",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
          }}
          aria-label="Refresh analytics"
        >
          <RefreshCw size={13} strokeWidth={2} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div
          className="rounded-xl p-4 mb-6 text-sm"
          style={{ background: "#edd8d2", color: "#7a3b2e" }}
        >
          ⚠ {error} — make sure uvicorn is running on port 8000.
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="flex items-center gap-3 py-10">
          <span className="w-5 h-5 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin" />
          <span className="text-sm" style={{ color: TEXT }}>Loading analytics…</span>
        </div>
      )}

      {/* Charts */}
      {!loading && data && (
        <div className="flex flex-col gap-6">

          {/* Bar chart — runs per user */}
          <Card title="Runs per Analyst" icon={BarChart2}>
            {hasUsers ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={data.by_user}
                  margin={{ top: 4, right: 8, left: -10, bottom: 0 }}
                  aria-label="Runs per analyst bar chart"
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis
                    dataKey="submitted_by"
                    tick={{ fontSize: 11, fill: MUTED, fontFamily: "var(--font-poppins)" }}
                    axisLine={{ stroke: GRID }}
                    tickLine={false}
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: MUTED, fontFamily: "var(--font-poppins)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="run_count" name="Runs" fill={TEAL} radius={[6, 6, 0, 0]} maxBarSize={56} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-center py-8" style={{ color: MUTED }}>
                No run data yet. Submit a briefing to see analytics.
              </p>
            )}

            {/* Table summary */}
            {hasUsers && (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-[12px]" style={{ color: TEXT }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${GRID}` }}>
                      <th className="text-left pb-2 font-semibold" style={{ fontFamily: "var(--font-poppins)" }}>Analyst</th>
                      <th className="text-right pb-2 font-semibold" style={{ fontFamily: "var(--font-poppins)" }}>Runs</th>
                      <th className="text-right pb-2 font-semibold" style={{ fontFamily: "var(--font-poppins)" }}>Avg Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_user.map((u) => (
                      <tr key={u.submitted_by} style={{ borderBottom: `1px solid ${GRID}44` }}>
                        <td className="py-1.5" style={{ color: TEXT }}>{u.submitted_by}</td>
                        <td className="py-1.5 text-right font-tabular" style={{ color: TEXT }}>{u.run_count}</td>
                        <td className="py-1.5 text-right font-tabular" style={{ color: MUTED }}>
                          {u.avg_duration_seconds > 0
                            ? `${u.avg_duration_seconds}s`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Line chart — daily trend */}
          <Card title="Daily Runs (Last 30 Days)" icon={TrendingUp}>
            {hasTrend ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart
                  data={data.daily_trend}
                  margin={{ top: 4, right: 8, left: -10, bottom: 0 }}
                  aria-label="Daily runs trend line chart"
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={GRID} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: MUTED, fontFamily: "var(--font-poppins)" }}
                    axisLine={{ stroke: GRID }}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fontSize: 11, fill: MUTED, fontFamily: "var(--font-poppins)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Line
                    type="monotone"
                    dataKey="run_count"
                    name="Runs"
                    stroke={AMBER}
                    strokeWidth={2.5}
                    dot={{ fill: AMBER, strokeWidth: 0, r: 4 }}
                    activeDot={{ r: 6, fill: GREEN }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-center py-8" style={{ color: MUTED }}>
                No runs in the last 30 days.
              </p>
            )}
          </Card>

        </div>
      )}
    </div>
  );
}
