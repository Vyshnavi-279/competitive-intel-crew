"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Calendar, MousePointer, ChevronRight, RefreshCw } from "lucide-react";
import { fetchKpis, listRuns } from "@/lib/api";
import { KpiDashboard } from "@/components/KpiDashboard";
import { StatusBadge } from "@/components/StatusBadge";
import { timeAgo } from "@/lib/utils";
import type { KpiData, RunSummary, RunStatus } from "@/lib/types";

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

  async function load(showRefresh = false) {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [kpiData, runData] = await Promise.all([fetchKpis(), listRuns(100)]);
      setKpis(kpiData);
      setRuns(runData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => { load(); }, []);

  const filtered = filter === "all" ? runs : runs.filter((r) => r.status === filter);

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="eyebrow mb-1">Analytics</p>
          <h1
            className="text-3xl font-semibold"
            style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#4A4438" }}
          >
            Dashboard
          </h1>
          <p className="mt-1 text-sm" style={{ color: "#8C8474" }}>
            Business KPIs and full run history at a glance.
          </p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing || loading}
          className="clay-knob flex items-center gap-2 px-4 py-2 text-[12px] font-semibold rounded-full hover:brightness-95 active:scale-95 transition-all disabled:opacity-50"
          style={{ color: "#4A4438", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
          aria-label="Refresh dashboard"
        >
          <RefreshCw size={13} strokeWidth={2} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="clay-raised p-4 mb-6 text-sm" style={{ color: "#C98B7A" }}>
          ⚠ {error} — is the backend running at port 8000?
        </div>
      )}

      {/* KPI section */}
      {loading && !kpis ? (
        <div className="clay-raised p-8 flex items-center gap-3 mb-6">
          <span className="w-5 h-5 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin" />
          <span className="text-sm" style={{ color: "#8C8474" }}>Loading KPIs…</span>
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
          <span className="text-xs" style={{ color: "#8C8474" }}>
            {runs.length} briefing{runs.length !== 1 ? "s" : ""} total
          </span>
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
                  ? { background: "#F7F2E9", color: "#4A4438", boxShadow: "4px 4px 8px rgba(74,68,56,0.2), -3px -3px 6px rgba(255,255,255,0.75)", fontFamily: "var(--font-poppins),sans-serif" }
                  : { background: "#EFE6D8", color: "#8C8474", boxShadow: "inset 3px 3px 6px rgba(74,68,56,0.12), inset -3px -3px 6px rgba(255,255,255,0.5)", fontFamily: "var(--font-poppins),sans-serif" }
                }
              >
                {label}
                <span className="text-[10px] px-1.5 py-0.5 rounded-full font-tabular"
                  style={{ background: active ? "#EFE6D8" : "#F7F2E9", color: "#8C8474" }}>
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
            <span className="text-sm" style={{ color: "#8C8474" }}>Loading runs…</span>
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div className="clay-raised p-10 text-center">
            <p className="text-sm" style={{ color: "#8C8474" }}>
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
                      ? <Calendar size={14} strokeWidth={2} color="#8C8474" />
                      : <MousePointer size={14} strokeWidth={2} color="#8C8474" />}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate"
                      style={{ color: "#4A4438", fontFamily: "var(--font-poppins),sans-serif" }}>
                      {run.topic}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      <span className="text-xs font-tabular" style={{ color: "#8C8474" }}>
                        {timeAgo(run.started_at)}
                      </span>
                      {run.sources_used > 0 && (
                        <span className="text-xs font-tabular" style={{ color: "#8C8474" }}>
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
                  <ChevronRight size={16} strokeWidth={2} color="#8C8474"
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
