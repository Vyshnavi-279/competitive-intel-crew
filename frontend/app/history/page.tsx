"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Calendar, MousePointer, ChevronRight } from "lucide-react";
import { listRuns } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { timeAgo } from "@/lib/utils";
import type { RunSummary, RunStatus } from "@/lib/types";

type FilterOption = "all" | RunStatus;

const FILTERS: { key: FilterOption; label: string }[] = [
  { key: "all",           label: "All"           },
  { key: "pending_review",label: "Pending Review" },
  { key: "published",     label: "Published"     },
  { key: "rejected",      label: "Rejected"      },
  { key: "running",       label: "Running"       },
  { key: "failed",        label: "Failed"        },
];

export default function HistoryPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterOption>("all");

  useEffect(() => {
    listRuns(100)
      .then(setRuns)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = filter === "all" ? runs : runs.filter((r) => r.status === filter);

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <p className="eyebrow mb-1">Dashboard</p>
        <h1
          className="text-3xl font-semibold"
          style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
        >
          Run History
        </h1>
        <p className="mt-1 text-sm" style={{ color: "#2E2A22" }}>
          {runs.length} briefing{runs.length !== 1 ? "s" : ""} total
        </p>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2 mb-6" role="group" aria-label="Filter runs">
        {FILTERS.map(({ key, label }) => {
          const active = filter === key;
          const count = key === "all" ? runs.length : runs.filter(r => r.status === key).length;
          if (count === 0 && key !== "all") return null;
          return (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-[12px] font-semibold rounded-full transition-all duration-150 hover:brightness-95 active:scale-95"
              style={
                active
                  ? {
                      background: "#F7F2E9",
                      color: "#2E2A22",
                      boxShadow: "4px 4px 8px rgba(74,68,56,0.2), -3px -3px 6px rgba(255,255,255,0.75)",
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    }
                  : {
                      background: "#EFE6D8",
                      color: "#2E2A22",
                      boxShadow: "inset 3px 3px 6px rgba(74,68,56,0.12), inset -3px -3px 6px rgba(255,255,255,0.5)",
                      fontFamily: "var(--font-poppins), Poppins, sans-serif",
                    }
              }
              aria-pressed={active}
            >
              {label}
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full font-tabular"
                style={{
                  background: active ? "#EFE6D8" : "#F7F2E9",
                  color: "#2E2A22",
                }}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Content */}
      {loading && (
        <div className="clay-raised p-8 flex items-center gap-3">
          <span className="w-5 h-5 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin" />
          <span className="text-sm" style={{ color: "#2E2A22" }}>Loading runs…</span>
        </div>
      )}

      {error && (
        <div className="clay-raised p-6 text-sm" style={{ color: "#C98B7A" }}>⚠ {error}</div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="clay-raised p-10 text-center">
          <p className="text-sm" style={{ color: "#2E2A22" }}>
            {filter === "all" ? "No runs yet. Start one from New Briefing." : `No ${filter.replace("_", " ")} runs.`}
          </p>
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <ul className="flex flex-col gap-3" aria-label="Run list">
          {filtered.map((run) => (
            <li key={run.run_id}>
              <Link
                href={`/runs/${run.run_id}`}
                className="clay-raised-sm flex items-center gap-4 px-5 py-4 hover:brightness-98 active:scale-[0.99] transition-all duration-150 group"
              >
                {/* Triggered-by knob */}
                <span
                  className={`clay-knob flex items-center justify-center w-9 h-9 shrink-0`}
                  aria-label={run.triggered_by === "scheduled" ? "Scheduled" : "Manual"}
                >
                  {run.triggered_by === "scheduled"
                    ? <Calendar size={14} strokeWidth={2} color="#4A4438" />
                    : <MousePointer size={14} strokeWidth={2} color="#4A4438" />
                  }
                </span>

                {/* Main content */}
                <div className="flex-1 min-w-0">
                  <p
                    className="text-sm font-semibold truncate"
                    style={{ color: "#2E2A22", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
                  >
                    {run.topic}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                    <span className="text-xs font-tabular" style={{ color: "#2E2A22" }}>
                      {timeAgo(run.started_at)}
                    </span>
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

                {/* Status badge */}
                <StatusBadge status={run.status} size="sm" />

                {/* Arrow */}
                <ChevronRight
                  size={16}
                  strokeWidth={2}
                  color="#4A4438"
                  className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
