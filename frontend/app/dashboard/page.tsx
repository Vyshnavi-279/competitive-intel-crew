"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Calendar, MousePointer, ChevronRight, RefreshCw } from "lucide-react";
import { fetchKpis, listRuns, deleteRun, deleteAllFailed } from "@/lib/api";
import { KpiDashboard } from "@/components/KpiDashboard";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDuration, timeAgo } from "@/lib/utils";
import type { KpiData, RunSummary, RunStatus } from "@/lib/types";
import { Trash2 } from "lucide-react";

type FilterOption = "all" | RunStatus;

const FILTERS: { key: FilterOption; label: string }[] = [
  { key: "all",            label: "All"           },
  { key: "pending_review", label: "Pending Review" },
  { key: "published",      label: "Published"     },
  { key: "rejected",       label: "Rejected"      },
  { key: "running",        label: "Running"       },
  { key: "failed",         label: "Failed"        },
];

export default function DashboardPage() {
  const [kpis, setKpis]       = useState<KpiData | null>(null);
  const [runs, setRuns]       = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [filter, setFilter]   = useState<FilterOption>("all");
  const [refreshing, setRefreshing] = useState(false);
  const [clearingFailed, setClearingFailed] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleClearFailed() {
    setClearingFailed(true);
    try {
      await deleteAllFailed();
      await load(true);
    } finally {
      setClearingFailed(false);
    }
  }

  async function handleDeleteRun(e: React.MouseEvent, runId: string) {
    e.preventDefault();
    e.stopPropagation();
    setDeletingId(runId);
    try {
      await deleteRun(runId);
      setRuns(prev => prev.filter(r => r.run_id !== runId));
    } finally {
      setDeletingId(null);
    }
  }

  async function load(showRefresh = false) {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [kpiData, runData] = await Promise.all([fetchKpis(), listRuns(100)]);
      setKpis(kpiData);
      setRuns(runData);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load dashboard data";
      setError(msg);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  // On mount: try immediately, then retry every 3 s until success (handles
  // the backend starting up a moment after the frontend).
  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    async function tryLoad() {
      if (cancelled) return;
      setLoading(true);
      setError(null);
      try {
        const [kpiData, runData] = await Promise.all([fetchKpis(), listRuns(100)]);
        if (!cancelled) {
          setKpis(kpiData);
          setRuns(runData);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setLoading(false);
          // Backend not ready yet — retry silently after 3 s (max 10 attempts)
          retryTimer = setTimeout(tryLoad, 3000);
        }
      }
    }

    // Give the backend 1 s head-start, then start polling
    retryTimer = setTimeout(tryLoad, 1000);
    return () => { cancelled = true; clearTimeout(retryTimer); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = filter === "all" ? runs : runs.filter((r) => r.status === filter);

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="eyebrow mb-1">Analytics</p>
          <h1
            className="text-3xl font-semibold"
            style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
          >
            Dashboard
          </h1>
          <p className="mt-1 text-sm" style={{ color: "#2E2A22" }}>
            Business KPIs and full run history at a glance.
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing || loading}
          className="clay-knob flex items-center gap-2 px-4 py-2 text-[12px] font-semibold rounded-full hover:brightness-95 active:scale-95 transition-all disabled:opacity-50"
          style={{ color: "#2E2A22", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
          aria-label="Refresh dashboard"
        >
          <RefreshCw size={13} strokeWidth={2} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="clay-raised p-4 mb-6 flex items-center justify-between gap-4">
          <p className="text-sm" style={{ color: "#C98B7A" }}>
            ⚠ Cannot reach the backend — make sure uvicorn is running on port 8000.
            <span className="block text-xs mt-0.5" style={{ color: "#2E2A22" }}>
              Run: <code className="font-mono bg-[#EFE6D8] px-1 rounded">uvicorn backend.main:app --reload --port 8000</code>
            </span>
          </p>
          <button
            onClick={() => load(true)}
            className="clay-knob shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold rounded-full hover:brightness-95 active:scale-95 transition-all"
            style={{ color: "#2E2A22", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
          >
            <RefreshCw size={11} strokeWidth={2} />
            Retry
          </button>
        </div>
      )}

      {/* KPI section */}
      {loading && !kpis ? (
        <div className="clay-raised p-8 flex items-center gap-3 mb-6">
          <span className="w-5 h-5 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin" />
          <span className="text-sm" style={{ color: "#2E2A22" }}>Loading KPIs…</span>
        </div>
      ) : kpis ? (
        <div className="mb-8">
          <KpiDashboard kpis={kpis} />
        </div>
      ) : null}

      {/* Run history */}
      <div>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <p className="eyebrow">Run History</p>
          <div className="flex items-center gap-3">
            <span className="text-xs" style={{ color: "#2E2A22" }}>
              {runs.length} briefing{runs.length !== 1 ? "s" : ""} total
            </span>
            {runs.some(r => r.status === "failed") && (
              <button
                onClick={handleClearFailed}
                disabled={clearingFailed}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold rounded-full hover:brightness-95 active:scale-95 transition-all disabled:opacity-50"
                style={{ background: "#edd8d2", color: "#7a3b2e", boxShadow: "3px 3px 6px rgba(74,68,56,0.15), -2px -2px 5px rgba(255,255,255,0.7)", fontFamily: "var(--font-poppins),sans-serif" }}
              >
                <Trash2 size={11} strokeWidth={2} />
                {clearingFailed ? "Clearing…" : "Clear all failed"}
              </button>
            )}
          </div>
        </div>

        {/* Filter chips */}
        <div className="flex flex-wrap gap-2 mb-5" role="group" aria-label="Filter runs">
          {FILTERS.map(({ key, label }) => {
            const active = filter === key;
            const count = key === "all" ? runs.length : runs.filter(r => r.status === key).length;
            if (count === 0 && key !== "all") return null;
            return (
              <button
                key={key}
                onClick={() => setFilter(key)}
                aria-pressed={active}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-[12px] font-semibold rounded-full transition-all duration-150 hover:brightness-95 active:scale-95"
                style={active
                  ? { background: "#F7F2E9", color: "#2E2A22", boxShadow: "4px 4px 8px rgba(74,68,56,0.2), -3px -3px 6px rgba(255,255,255,0.75)", fontFamily: "var(--font-poppins),sans-serif" }
                  : { background: "#EFE6D8", color: "#2E2A22", boxShadow: "inset 3px 3px 6px rgba(74,68,56,0.12), inset -3px -3px 6px rgba(255,255,255,0.5)", fontFamily: "var(--font-poppins),sans-serif" }
                }
              >
                {label}
                <span className="text-[10px] px-1.5 py-0.5 rounded-full font-tabular"
                  style={{ background: active ? "#EFE6D8" : "#F7F2E9", color: "#2E2A22" }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Run list */}
        {loading && (
          <div className="clay-raised p-8 flex items-center gap-3">
            <span className="w-5 h-5 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin" />
            <span className="text-sm" style={{ color: "#2E2A22" }}>Loading runs…</span>
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div className="clay-raised p-10 text-center">
            <p className="text-sm" style={{ color: "#2E2A22" }}>
              {filter === "all"
                ? "No runs yet. Start one from New Briefing."
                : `No ${filter.replace("_", " ")} runs.`}
            </p>
          </div>
        )}

        {!loading && filtered.length > 0 && (
          <ul className="flex flex-col gap-3" aria-label="Run list">
            {filtered.map((run) => (
              <li key={run.run_id}>
                <Link
                  href={`/runs/${run.run_id}`}
                  className="clay-raised-sm flex items-center gap-4 px-5 py-4 hover:brightness-98 active:scale-[0.99] transition-all duration-150 group"
                >
                  <span className="clay-knob flex items-center justify-center w-9 h-9 shrink-0">
                    {run.triggered_by === "scheduled"
                      ? <Calendar size={14} strokeWidth={2} color="#4A4438" />
                      : <MousePointer size={14} strokeWidth={2} color="#4A4438" />}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate"
                      style={{ color: "#2E2A22", fontFamily: "var(--font-poppins),sans-serif" }}>
                      {run.topic}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-xs font-tabular" style={{ color: "#2E2A22" }}>
                        {timeAgo(run.started_at)}
                      </span>
                      {run.duration_seconds != null && (
                        <span className="text-xs font-tabular" style={{ color: "#2E2A22" }}>
                          · {formatDuration(run.duration_seconds)}
                        </span>
                      )}
                      {run.sources_used > 0 && (
                        <span className="text-xs font-tabular" style={{ color: "#2E2A22" }}>
                          · {run.sources_used} sources
                        </span>
                      )}
                      {run.sources_skipped_count > 0 && (
                        <span className="text-xs font-tabular" style={{ color: "#C98B7A" }}>
                          · {run.sources_skipped_count} skipped
                        </span>
                      )}
                    </div>
                  </div>
                  <StatusBadge status={run.status} size="sm" />
                  <button
                    onClick={(e) => handleDeleteRun(e, run.run_id)}
                    disabled={deletingId === run.run_id}
                    className="shrink-0 p-1.5 rounded-full opacity-0 group-hover:opacity-100 hover:brightness-95 active:scale-95 transition-all disabled:opacity-50"
                    style={{ color: "#C98B7A" }}
                    aria-label="Delete run"
                    title="Delete this run"
                  >
                    {deletingId === run.run_id
                      ? <span className="w-3 h-3 rounded-full border border-current border-t-transparent animate-spin block" />
                      : <Trash2 size={13} strokeWidth={2} />
                    }
                  </button>
                  <ChevronRight size={16} strokeWidth={2} color="#4A4438"
                    className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
