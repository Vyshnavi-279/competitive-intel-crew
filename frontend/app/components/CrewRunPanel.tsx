"use client";

// app/components/CrewRunPanel.tsx
// Left sidebar — topic input, agent status pills, reliability stats, run history.
//
// State machine per run:
//   idle → [user submits] → coordinator running → researcher running
//        → analyst running → writer running → done / error
//
// The crew is a black box from the frontend perspective: we don't get
// streaming agent events, so we simulate progress by advancing through
// agents on a timer once the POST /api/run call is in-flight.
// When the call resolves, all agents flip to "done".

import { useEffect, useRef, useState } from "react";
import {
  CheckCircle,
  ChevronRight,
  Clock,
  Database,
  Loader,
  Play,
  RefreshCw,
  XCircle,
  Zap,
} from "lucide-react";
import { getRuns, runBriefing } from "@/app/lib/api";
import type {
  AgentName,
  AgentStatus,
  AgentStatusMap,
  Briefing,
  RunSummary,
} from "@/app/lib/types";
import { AGENT_NAMES } from "@/app/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const IDLE_AGENTS: AgentStatusMap = {
  Coordinator: "idle",
  Researcher: "idle",
  Analyst: "idle",
  Writer: "idle",
};

function statusColor(s: AgentStatus): string {
  switch (s) {
    case "running": return "bg-teal-500 text-white";
    case "done":    return "bg-teal-900/80 text-teal-300 border border-teal-700/50";
    case "error":   return "bg-red-900/60 text-red-300 border border-red-700/50";
    default:        return "bg-[#0a1929] text-slate-500 border border-[#1e3a54]";
  }
}

function StatusIcon({ status }: { status: AgentStatus }) {
  switch (status) {
    case "running":
      return <Loader className="w-3 h-3 animate-spin" />;
    case "done":
      return <CheckCircle className="w-3 h-3" />;
    case "error":
      return <XCircle className="w-3 h-3" />;
    default:
      return <span className="w-3 h-3 rounded-full border border-slate-600 inline-block" />;
  }
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtDuration(s: number | null): string {
  if (s === null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

function statusDot(status: string): string {
  switch (status) {
    case "completed":
    case "published":   return "bg-teal-400";
    case "running":     return "bg-teal-400 animate-pulse";
    case "failed":      return "bg-red-400";
    default:            return "bg-amber-400";
  }
}

// ---------------------------------------------------------------------------
// CrewRunPanel
// ---------------------------------------------------------------------------

interface CrewRunPanelProps {
  /** Called when a run completes or a history item is clicked */
  onBriefingLoaded: (briefing: Briefing) => void;
  activeRunId?: string;
}

export default function CrewRunPanel({
  onBriefingLoaded,
  activeRunId,
}: CrewRunPanelProps) {
  const [topic, setTopic] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agents, setAgents] = useState<AgentStatusMap>({ ...IDLE_AGENTS });
  const [currentBriefing, setCurrentBriefing] = useState<Briefing | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  // Timer ref for the simulated agent progress
  const progressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const agentIndexRef = useRef(0);

  // Load run history on mount
  useEffect(() => {
    getRuns(30)
      .then(setHistory)
      .catch(() => {/* backend might be offline */})
      .finally(() => setHistoryLoading(false));
  }, []);

  // Refresh history after a run completes
  function refreshHistory() {
    getRuns(30).then(setHistory).catch(() => {});
  }

  // Simulate agent progression while the POST /api/run call is in-flight
  function startAgentSimulation() {
    agentIndexRef.current = 0;
    setAgents({ ...IDLE_AGENTS, Coordinator: "running" });

    function advance() {
      agentIndexRef.current += 1;
      const idx = agentIndexRef.current;
      if (idx >= AGENT_NAMES.length) return;

      setAgents((prev) => {
        const next = { ...prev };
        // Mark previous agent done
        if (idx > 0) next[AGENT_NAMES[idx - 1]] = "done";
        next[AGENT_NAMES[idx]] = "running";
        return next;
      });

      // Advance every ~8s to roughly match a 30-40s run
      progressTimer.current = setTimeout(advance, 8000);
    }
    progressTimer.current = setTimeout(advance, 8000);
  }

  function finishAgentSimulation(success: boolean) {
    if (progressTimer.current) {
      clearTimeout(progressTimer.current);
      progressTimer.current = null;
    }
    if (success) {
      setAgents({
        Coordinator: "done",
        Researcher: "done",
        Analyst: "done",
        Writer: "done",
      });
    } else {
      // Mark the currently-running agent as errored
      setAgents((prev) => {
        const next = { ...prev } as AgentStatusMap;
        for (const name of AGENT_NAMES) {
          if (prev[name] === "running") next[name] = "error";
        }
        return next;
      });
    }
  }

  async function handleRun() {
    const trimmed = topic.trim();
    if (!trimmed || isRunning) return;

    setIsRunning(true);
    setError(null);
    startAgentSimulation();

    try {
      const briefing = await runBriefing(trimmed);
      finishAgentSimulation(true);
      setCurrentBriefing(briefing);
      onBriefingLoaded(briefing);
      refreshHistory();
    } catch (err: unknown) {
      finishAgentSimulation(false);
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setIsRunning(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun();
  }

  const meta = currentBriefing?.metadata;

  return (
    <aside className="flex flex-col h-full bg-[#0f1b2d] border-r border-[#1a2e47] overflow-y-auto">

      {/* Branding */}
      <div className="px-5 pt-5 pb-4 border-b border-[#1a2e47]">
        <div className="flex items-center gap-2 mb-0.5">
          <Zap className="w-4 h-4 text-teal-400" />
          <span className="text-xs font-bold uppercase tracking-widest text-teal-400">
            MarketPulse
          </span>
        </div>
        <p className="text-[11px] text-slate-500">Competitive Intelligence Crew</p>
      </div>

      {/* Topic input */}
      <div className="px-4 py-4 border-b border-[#1a2e47]">
        <label className="text-[11px] uppercase tracking-wider text-slate-500 block mb-2">
          Topic
        </label>
        <textarea
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. AI developer tools market Q3 2025"
          rows={3}
          disabled={isRunning}
          className="
            w-full px-3 py-2.5 rounded-lg text-sm text-slate-200 placeholder-slate-600
            bg-[#0a1929] border border-[#1e3a54] focus:border-teal-600 focus:ring-1
            focus:ring-teal-600/40 focus:outline-none resize-none transition-colors
            disabled:opacity-50
          "
        />
        <p className="text-[10px] text-slate-600 mt-1.5">⌘+Enter to run</p>

        <button
          onClick={handleRun}
          disabled={isRunning || !topic.trim()}
          className="
            mt-3 w-full flex items-center justify-center gap-2
            px-4 py-2.5 rounded-lg text-sm font-semibold
            bg-teal-600 hover:bg-teal-500 disabled:bg-teal-900/40
            text-white disabled:text-teal-700
            transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500/50
          "
        >
          {isRunning ? (
            <>
              <Loader className="w-4 h-4 animate-spin" />
              Running crew…
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Run Briefing
            </>
          )}
        </button>

        {error && (
          <div className="mt-2 px-3 py-2 rounded-lg bg-red-900/30 border border-red-700/40 text-xs text-red-400">
            {error}
          </div>
        )}
      </div>

      {/* Agent status */}
      <div className="px-4 py-4 border-b border-[#1a2e47]">
        <p className="text-[11px] uppercase tracking-wider text-slate-500 mb-3">
          Agents
        </p>
        <ul className="space-y-2">
          {AGENT_NAMES.map((name: AgentName, i) => (
            <li key={name} className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-slate-600 w-4">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-sm text-slate-300">{name}</span>
              </div>
              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wide ${statusColor(agents[name])}`}>
                <StatusIcon status={agents[name]} />
                {agents[name]}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Reliability block (only when a run has completed) */}
      {meta && (
        <div className="px-4 py-4 border-b border-[#1a2e47]">
          <p className="text-[11px] uppercase tracking-wider text-slate-500 mb-3">
            Reliability
          </p>
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Sources attempted</span>
              <span className="text-slate-300 font-mono">{meta.sources_attempted}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Sources used</span>
              <span className="text-teal-400 font-mono">{meta.sources_used}</span>
            </div>
            {meta.sources_skipped.length > 0 && (
              <div className="flex justify-between text-xs">
                <span className="text-amber-400/80">Skipped</span>
                <span className="text-amber-400 font-mono">{meta.sources_skipped.length}</span>
              </div>
            )}
            <div className="flex justify-between text-xs">
              <span className="text-slate-500">Citations check</span>
              {currentBriefing?.sections.every((s) =>
                s.claims.every((c) => c.citations.length > 0)
              ) ? (
                <span className="text-teal-400 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" /> All pass
                </span>
              ) : (
                <span className="text-amber-400 flex items-center gap-1">
                  <XCircle className="w-3 h-3" /> Some fail
                </span>
              )}
            </div>
          </div>

          {/* Run stats */}
          <div className="mt-3 pt-3 border-t border-[#1a2e47] grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-[#0a1929] px-2.5 py-2 border border-[#1e3a54]">
              <p className="text-[10px] text-slate-500">Duration</p>
              <p className="text-sm font-mono text-slate-300 mt-0.5 flex items-center gap-1">
                <Clock className="w-3 h-3 text-teal-500" />
                {fmtDuration(meta.duration_seconds)}
              </p>
            </div>
            <div className="rounded-lg bg-[#0a1929] px-2.5 py-2 border border-[#1e3a54]">
              <p className="text-[10px] text-slate-500">Steps</p>
              <p className="text-sm font-mono text-slate-300 mt-0.5 flex items-center gap-1">
                <Database className="w-3 h-3 text-teal-500" />
                {meta.total_steps}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Run history */}
      <div className="flex-1 px-4 py-4">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[11px] uppercase tracking-wider text-slate-500">
            History
          </p>
          <button
            onClick={refreshHistory}
            className="text-slate-600 hover:text-slate-400 transition-colors"
            title="Refresh history"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {historyLoading ? (
          <div className="flex items-center gap-2 text-xs text-slate-600 py-2">
            <Loader className="w-3 h-3 animate-spin" /> Loading…
          </div>
        ) : history.length === 0 ? (
          <p className="text-xs text-slate-600 italic py-2">No runs yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {history.map((run) => (
              <li key={run.run_id}>
                <button
                  onClick={async () => {
                    try {
                      const { getRun } = await import("@/app/lib/api");
                      const b = await getRun(run.run_id);
                      onBriefingLoaded(b);
                    } catch {
                      /* silent */
                    }
                  }}
                  className={`
                    w-full text-left px-3 py-2.5 rounded-lg border transition-colors group
                    ${activeRunId === run.run_id
                      ? "bg-teal-900/30 border-teal-700/50"
                      : "bg-[#0a1929] border-[#1e3a54] hover:border-teal-800"
                    }
                  `}
                >
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-medium text-slate-300 truncate pr-2 max-w-[85%]">
                      {run.topic}
                    </p>
                    <ChevronRight className="w-3 h-3 text-slate-600 flex-shrink-0 group-hover:text-teal-500 transition-colors" />
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusDot(run.status)}`} />
                    <span className="text-[10px] text-slate-500 capitalize">{run.status}</span>
                    <span className="text-[10px] text-slate-600">·</span>
                    <span className="text-[10px] text-slate-500">{fmtDate(run.started_at)}</span>
                    {run.sources_skipped_count > 0 && (
                      <>
                        <span className="text-[10px] text-slate-600">·</span>
                        <span className="text-[10px] text-amber-500">
                          {run.sources_skipped_count} skipped
                        </span>
                      </>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
