"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { getRun } from "@/lib/api";
import { formatDuration, timeAgo } from "@/lib/utils";
import { AgentChain, buildAgentNodes } from "@/components/AgentChain";
import { StatusBadge } from "@/components/StatusBadge";
import type { Briefing } from "@/lib/types";

const POLL_INTERVAL_MS = 3000;

interface RunMonitorProps {
  runId: string;
  /** Optional initial briefing data from server-side fetch to avoid double-fetching */
  initialBriefing?: Briefing | null;
}

export function RunMonitor({ runId, initialBriefing }: RunMonitorProps) {
  const router = useRouter();
  const [briefing, setBriefing] = useState<Briefing | null>(initialBriefing ?? null);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);

  const fetchRun = useCallback(async () => {
    try {
      const data = await getRun(runId);
      setBriefing(data);

      // Accumulate synthetic log messages from what we can observe
      const m = data.metadata;
      const newLogs: string[] = [];
      if (m.sources_used > 0) newLogs.push(`✓ ${m.sources_used} sources retrieved`);
      if (m.sources_skipped?.length > 0)
        newLogs.push(`⚠ ${m.sources_skipped.length} sources skipped`);
      if (data.unverified_flags?.length > 0)
        newLogs.push(...data.unverified_flags.slice(0, 5).map((f) => `⚠ ${f}`));
      if (m.status !== "running")
        newLogs.push(`● Run ${m.status} in ${formatDuration(m.duration_seconds)}`);

      setLogs(newLogs);
      return data.metadata.status;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error fetching run");
      return "failed";
    }
  }, [runId]);

  useEffect(() => {
    // Use a ref-like variable to prevent multiple redirects
    let redirectScheduled = false;
    const interval = { id: undefined as ReturnType<typeof setInterval> | undefined };

    const poll = async () => {
      const status = await fetchRun();
      if (status !== "running") {
        // Stop polling
        if (interval.id !== undefined) {
          clearInterval(interval.id);
          interval.id = undefined;
        }
        // Redirect to detail page after a short delay (only once, only if not failed)
        if (status !== "failed" && !redirectScheduled) {
          redirectScheduled = true;
          setTimeout(() => router.push(`/runs/${runId}`), 1200);
        }
      }
    };

    poll(); // immediate first fetch
    interval.id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (interval.id !== undefined) clearInterval(interval.id);
    };
  }, [fetchRun, runId, router]);

  if (error) {
    return (
      <div className="clay-raised p-6 text-sm" style={{ color: "#C98B7A" }}>
        ⚠ {error}
      </div>
    );
  }

  if (!briefing) {
    return (
      <div className="clay-raised p-8 flex items-center gap-3">
        <span className="w-5 h-5 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin" />
        <span className="text-sm" style={{ color: "#8C8474" }}>Connecting…</span>
      </div>
    );
  }

  const m = briefing.metadata;
  const agents = buildAgentNodes(m.status, m.sources_used);
  const isRunning = m.status === "running";

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="clay-raised p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="eyebrow mb-1">
              {isRunning ? "Running now" : "Run complete"}
            </p>
            <h2
              className="text-xl font-semibold leading-snug"
              style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#4A4438" }}
            >
              {m.topic}
            </h2>
            <p className="text-xs mt-1" style={{ color: "#8C8474" }}>
              Started {timeAgo(m.started_at)}
              {m.duration_seconds != null && ` · ${formatDuration(m.duration_seconds)}`}
            </p>
          </div>
          <StatusBadge status={m.status} />
        </div>
      </div>

      {/* Agent chain */}
      <div className="clay-raised p-6">
        <p className="eyebrow mb-5">Agent Pipeline</p>
        <AgentChain agents={agents} />
      </div>

      {/* Live log strip */}
      <div className="clay-inset rounded-[20px] p-5">
        <p className="eyebrow mb-3">Activity Log</p>
        {logs.length === 0 ? (
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full border-2 border-[#93B6C4] border-t-transparent animate-spin" />
            <span className="text-xs" style={{ color: "#8C8474", fontFamily: "monospace" }}>
              Agents initialising…
            </span>
          </div>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {logs.map((log, i) => (
              <li
                key={i}
                className="text-xs"
                style={{ color: "#8C8474", fontFamily: "monospace" }}
              >
                {log}
              </li>
            ))}
            {isRunning && (
              <li className="flex items-center gap-1.5 text-xs" style={{ color: "#93B6C4", fontFamily: "monospace" }}>
                <span className="w-2 h-2 rounded-full border border-current border-t-transparent animate-spin" />
                Processing…
              </li>
            )}
          </ul>
        )}
      </div>

      {/* Done — redirect note */}
      {!isRunning && m.status !== "failed" && (
        <p className="text-xs text-center" style={{ color: "#8C8474" }}>
          Redirecting to briefing…
        </p>
      )}
      {m.status === "failed" && (
        <div className="clay-raised--rejected p-4 rounded-[24px]">
          <p className="text-sm font-medium" style={{ color: "#7a3b2e" }}>
            Run failed
          </p>
          {briefing.unverified_flags.map((f, i) => (
            <p key={i} className="text-xs mt-1" style={{ color: "#8C8474" }}>{f}</p>
          ))}
        </div>
      )}
    </div>
  );
}
