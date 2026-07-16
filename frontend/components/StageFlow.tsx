"use client";

/**
 * StageFlow — Phase 1 addition.
 *
 * A horizontal stepper showing the 5 pipeline stages:
 *   Coordinator → Researcher → Analyst → Fact-Checker → Writer
 *
 * Polls GET /api/runs/{runId}/stages every 2 s while the run status is
 * "running".  Stops polling once the run reaches a terminal status.
 * Each node expands on click/hover to show description + timestamps.
 *
 * This component is purely additive — it renders in empty space above the
 * main briefing content and does not replace or rearrange anything.
 */

import { useEffect, useRef, useState } from "react";
import { CheckCircle, Loader, XCircle, Circle, ChevronDown, ChevronUp } from "lucide-react";
import type { RunStatus } from "@/lib/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StageStatus = "pending" | "running" | "done" | "failed";

interface StageEntry {
  stage_name: string;
  status: StageStatus;
  description: string;
  started_at: string | null;
  completed_at: string | null;
}

interface StageFlowProps {
  runId: string;
  runStatus: RunStatus;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TERMINAL_STATUSES: RunStatus[] = [
  "completed",
  "failed",
  "published",
  "pending_review",
  "rejected",
];

/** All 5 stages in canonical order (shown as skeleton nodes before data arrives). */
const STAGE_NAMES = [
  "Coordinator",
  "Researcher",
  "Analyst",
  "Fact-Checker",
  "Writer",
];

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}

function elapsed(started: string | null, completed: string | null): string | null {
  if (!started) return null;
  try {
    const end = completed ? new Date(completed) : new Date();
    const secs = Math.round((end.getTime() - new Date(started).getTime()) / 1000);
    if (secs < 60) return `${secs}s`;
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Status icon
// ---------------------------------------------------------------------------

function StatusIcon({ status, size = 18 }: { status: StageStatus; size?: number }) {
  if (status === "done") {
    return <CheckCircle size={size} strokeWidth={2} color="#6fa87a" />;
  }
  if (status === "running") {
    return (
      <Loader
        size={size}
        strokeWidth={2}
        color="#93B6C4"
        className="animate-spin"
        style={{ animationDuration: "1.2s" }}
      />
    );
  }
  if (status === "failed") {
    return <XCircle size={size} strokeWidth={2} color="#C98B7A" />;
  }
  // pending
  return <Circle size={size} strokeWidth={1.5} color="#B8AFA4" />;
}

// ---------------------------------------------------------------------------
// Single Stage Node
// ---------------------------------------------------------------------------

function StageNode({
  entry,
  isLast,
}: {
  entry: StageEntry;
  isLast: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = entry.status === "running";

  const nodeColor =
    entry.status === "done"
      ? "#A9C6AE"
      : entry.status === "running"
      ? "#93B6C4"
      : entry.status === "failed"
      ? "#C98B7A"
      : "#D6CEC4";

  return (
    <div className="flex items-start gap-0" style={{ flex: 1, minWidth: 0 }}>
      {/* Node + connector */}
      <div className="flex flex-col items-center" style={{ minWidth: 0, flex: 1 }}>
        {/* Clickable node */}
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={`${entry.stage_name} — ${entry.status}. Click to ${expanded ? "collapse" : "expand"} details.`}
          className="flex flex-col items-center gap-1.5 group cursor-pointer focus:outline-none w-full"
          style={{ minWidth: 0 }}
        >
          {/* Circle indicator */}
          <div
            className="flex items-center justify-center w-10 h-10 rounded-full transition-all duration-200"
            style={{
              background: `${nodeColor}22`,
              boxShadow: isRunning
                ? `0 0 0 3px ${nodeColor}44, 3px 3px 8px rgba(74,68,56,0.18), -2px -2px 6px rgba(255,255,255,0.7)`
                : `3px 3px 8px rgba(74,68,56,0.18), -2px -2px 6px rgba(255,255,255,0.7)`,
              border: `2px solid ${nodeColor}66`,
            }}
          >
            <StatusIcon status={entry.status} size={18} />
          </div>

          {/* Stage name */}
          <span
            className="text-[11px] font-semibold text-center leading-tight px-1 truncate w-full"
            style={{
              color: entry.status === "pending" ? "#9A9086" : "#2E2A22",
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
            }}
          >
            {entry.stage_name}
          </span>

          {/* Expand toggle */}
          <span className="opacity-40 group-hover:opacity-80 transition-opacity" aria-hidden="true">
            {expanded ? (
              <ChevronUp size={11} strokeWidth={2} color="#4A4438" />
            ) : (
              <ChevronDown size={11} strokeWidth={2} color="#4A4438" />
            )}
          </span>
        </button>

        {/* Expanded detail card */}
        {expanded && (
          <div
            className="mt-2 rounded-xl px-3 py-2.5 text-left w-full max-w-[160px]"
            style={{
              background: "#F7F2E9",
              boxShadow: "3px 3px 8px rgba(74,68,56,0.15), -2px -2px 6px rgba(255,255,255,0.7)",
              zIndex: 10,
              position: "relative",
            }}
          >
            <p
              className="text-[11px] font-medium leading-snug mb-1.5"
              style={{ color: "#2E2A22", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
            >
              {entry.description || "No description available."}
            </p>
            <div className="flex flex-col gap-0.5">
              <p className="text-[10px] font-tabular" style={{ color: "#6B6358" }}>
                Started: {fmtTime(entry.started_at)}
              </p>
              {entry.status === "done" || entry.status === "failed" ? (
                <p className="text-[10px] font-tabular" style={{ color: "#6B6358" }}>
                  Ended: {fmtTime(entry.completed_at)}
                </p>
              ) : null}
              {entry.started_at && (
                <p className="text-[10px] font-tabular" style={{ color: "#6B6358" }}>
                  Duration: {elapsed(entry.started_at, entry.completed_at) ?? "—"}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Connector line (not shown for the last node) */}
      {!isLast && (
        <div
          className="mt-5 shrink-0"
          style={{
            width: 32,
            height: 2,
            background: entry.status === "done" ? "#A9C6AE88" : "#D6CEC4",
            borderRadius: 1,
            alignSelf: "flex-start",
            marginTop: "18px",
          }}
          aria-hidden="true"
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function StageFlow({ runId, runStatus }: StageFlowProps) {
  const [stages, setStages] = useState<StageEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isTerminal = TERMINAL_STATUSES.includes(runStatus);

  // Build a map of stage name → entry for merging with skeleton list
  const stageMap = new Map(stages.map((s) => [s.stage_name, s]));

  // Merge fetched stages with the skeleton so all 5 nodes always show
  const displayStages: StageEntry[] = STAGE_NAMES.map((name) => {
    return (
      stageMap.get(name) ?? {
        stage_name: name,
        status: "pending" as StageStatus,
        description: "",
        started_at: null,
        completed_at: null,
      }
    );
  });

  async function fetchStages() {
    try {
      const API_BASE =
        process.env.NEXT_PUBLIC_API_URL ?? "https://competitive-intel-crew-2.onrender.com";
      const res = await fetch(`${API_BASE}/api/runs/${runId}/stages`);
      if (!res.ok) return;
      const data: StageEntry[] = await res.json();
      setStages(data);
    } catch {
      // Silently ignore — network errors during polling shouldn't break the page
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStages();

    if (!isTerminal) {
      // Poll every 2 s while run is active
      intervalRef.current = setInterval(fetchStages, 2000);
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, isTerminal]);

  // Stop polling once we reach a terminal status
  useEffect(() => {
    if (isTerminal && intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
      // Do one final fetch to get the completed state
      fetchStages();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTerminal]);

  return (
    <div
      className="rounded-[20px] p-5"
      style={{
        background: "linear-gradient(145deg, #F7F2E9, #EDE4D4)",
        boxShadow:
          "4px 4px 12px rgba(74,68,56,0.15), -3px -3px 9px rgba(255,255,255,0.75)",
      }}
      aria-label="Pipeline stage progress"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <p
          className="text-[11px] font-bold tracking-widest uppercase"
          style={{
            color: "#9A9086",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
            letterSpacing: "0.1em",
          }}
        >
          Pipeline Stages
        </p>
        {!isTerminal && (
          <span
            className="flex items-center gap-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full"
            style={{ background: "#93B6C422", color: "#5a8fa0" }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: "#93B6C4" }}
              aria-hidden="true"
            />
            Live
          </span>
        )}
      </div>

      {/* Stage nodes */}
      {loading && stages.length === 0 ? (
        <div className="flex items-center gap-2 py-2">
          <span
            className="w-4 h-4 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin"
            aria-hidden="true"
          />
          <span className="text-[12px]" style={{ color: "#6B6358" }}>
            Loading stages…
          </span>
        </div>
      ) : (
        <div className="flex items-start overflow-x-auto pb-1">
          {displayStages.map((stage, i) => (
            <StageNode
              key={stage.stage_name}
              entry={stage}
              isLast={i === displayStages.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
