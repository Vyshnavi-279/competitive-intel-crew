"use client";

// app/page.tsx
// MarketPulse — Weekly Competitive Brief dashboard.
//
// Layout (≥ lg screens):
//   ┌──────────────┬──────────────────────────────────┬──────────────┐
//   │ CrewRunPanel │       3 × BriefingCard           │ Reliability  │
//   │  (fixed 280) │  (scrollable, Executive Summary  │   Panel      │
//   │              │   featured at top)               │  (fixed 300) │
//   └──────────────┴──────────────────────────────────┴──────────────┘
//
// Mobile: all panels stack vertically.

import { useCallback, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  CheckCircle,
  Clock,
  Loader,
  Rss,
} from "lucide-react";

import BriefingCard from "@/app/components/BriefingCard";
import CrewRunPanel from "@/app/components/CrewRunPanel";
import ReliabilityPanel from "@/app/components/ReliabilityPanel";
import type { Briefing } from "@/app/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SECTION_ORDER = [
  "Executive Summary",
  "Competitor Pricing & Product Moves",
  "Market Signals",
] as const;

function fmtRunDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtWeek(iso: string): string {
  try {
    const d = new Date(iso);
    const oneJan = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil(
      ((d.getTime() - oneJan.getTime()) / 86400000 + oneJan.getDay() + 1) / 7
    );
    return `W${week} · ${d.getFullYear()}`;
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// Empty / loading state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center px-8">
      <div className="w-16 h-16 rounded-2xl bg-[#0a1929] border border-[#1e3a54] flex items-center justify-center mb-5 shadow-[0_0_40px_rgba(20,184,166,0.08)]">
        <Rss className="w-7 h-7 text-teal-500/60" />
      </div>
      <h2 className="text-lg font-semibold text-slate-400 mb-2">
        No briefing loaded
      </h2>
      <p className="text-sm text-slate-600 max-w-xs leading-relaxed">
        Enter a topic in the left panel and click{" "}
        <span className="text-teal-500 font-medium">Run Briefing</span> to
        generate a competitive intelligence report, or select a past run from
        the history list.
      </p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-teal-900/50 text-teal-400 border border-teal-700/40">
          <CheckCircle className="w-3.5 h-3.5" /> Completed
        </span>
      );
    case "published":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-teal-900/50 text-teal-300 border border-teal-600/40">
          <CheckCircle className="w-3.5 h-3.5" /> Published
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-900/40 text-red-400 border border-red-700/40">
          <AlertTriangle className="w-3.5 h-3.5" /> Failed
        </span>
      );
    case "running":
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-teal-900/40 text-teal-400 border border-teal-700/40 animate-pulse">
          <Loader className="w-3.5 h-3.5 animate-spin" /> Running
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-900/40 text-amber-400 border border-amber-700/40">
          <Clock className="w-3.5 h-3.5" /> {status}
        </span>
      );
  }
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | undefined>();

  const handleBriefingLoaded = useCallback((b: Briefing) => {
    setBriefing(b);
    setActiveRunId(b.metadata.run_id);
  }, []);

  // Sort sections into the canonical order, ignoring sections with unexpected titles
  const orderedSections = briefing
    ? SECTION_ORDER.flatMap((title) => {
        const found = briefing.sections.find((s) => s.title === title);
        return found ? [found] : [];
      })
    : [];

  const meta = briefing?.metadata;

  return (
    <div className="flex h-screen bg-[#080f1a] text-white overflow-hidden">

      {/* ── Left sidebar ───────────────────────────────────────────────── */}
      <div className="w-72 flex-shrink-0 h-full overflow-hidden">
        <CrewRunPanel
          onBriefingLoaded={handleBriefingLoaded}
          activeRunId={activeRunId}
        />
      </div>

      {/* ── Main content area ──────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Header */}
        <header className="flex-shrink-0 px-6 py-4 border-b border-[#1a2e47] bg-[#0a1420]">
          {meta ? (
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                {/* Week label */}
                <div className="flex items-center gap-2 mb-1">
                  <Calendar className="w-3.5 h-3.5 text-teal-500 flex-shrink-0" />
                  <span className="text-xs font-mono text-teal-500 uppercase tracking-widest">
                    {fmtWeek(meta.started_at)}
                  </span>
                  <span className="text-[11px] text-slate-600">
                    {fmtRunDate(meta.started_at)}
                  </span>
                </div>
                {/* Topic */}
                <h1 className="text-lg font-bold text-slate-100 truncate leading-tight">
                  {meta.topic}
                </h1>
              </div>

              {/* Meta badges */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <StatusBadge status={meta.status} />
                {meta.duration_seconds !== null && (
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {Math.round(meta.duration_seconds)}s
                  </span>
                )}
                {meta.sources_skipped.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-xs text-amber-400">
                    <AlertTriangle className="w-3 h-3" />
                    {meta.sources_skipped.length} skipped
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 rounded bg-teal-500/20 flex items-center justify-center">
                <Rss className="w-3 h-3 text-teal-500" />
              </div>
              <span className="text-sm font-semibold text-slate-400">
                MarketPulse — Weekly Competitive Brief
              </span>
            </div>
          )}
        </header>

        {/* Scrollable content + right rail */}
        <div className="flex-1 flex min-h-0 overflow-hidden">

          {/* Briefing sections */}
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4 min-w-0">
            {briefing === null ? (
              <EmptyState />
            ) : briefing.metadata.status === "failed" ? (
              <div className="flex flex-col items-center justify-center min-h-[300px] text-center px-6">
                <AlertTriangle className="w-10 h-10 text-red-400 mb-3" />
                <h2 className="text-base font-semibold text-red-300 mb-2">
                  Run Failed
                </h2>
                {briefing.unverified_flags.length > 0 && (
                  <p className="text-sm text-slate-500 max-w-md">
                    {briefing.unverified_flags[0]}
                  </p>
                )}
              </div>
            ) : orderedSections.length === 0 ? (
              <div className="flex items-center justify-center min-h-[300px]">
                <p className="text-sm text-slate-500 italic">
                  No sections were parsed from this run.
                </p>
              </div>
            ) : (
              <>
                {orderedSections.map((section, i) => (
                  <BriefingCard
                    key={section.title}
                    section={section}
                    featured={i === 0} // Executive Summary is featured
                  />
                ))}

                {/* Run ID footer */}
                <p className="text-[10px] text-slate-700 font-mono pt-2 pb-4">
                  run: {meta?.run_id}
                </p>
              </>
            )}
          </div>

          {/* ── Right rail — Reliability panel (hidden on narrow screens) ─ */}
          {briefing && (
            <aside className="hidden xl:block w-80 flex-shrink-0 overflow-y-auto px-4 py-5 border-l border-[#1a2e47]">
              <ReliabilityPanel briefing={briefing} />
            </aside>
          )}
        </div>

        {/* Mobile reliability panel — appears below briefing on small screens */}
        {briefing && (
          <div className="xl:hidden px-4 py-4 border-t border-[#1a2e47]">
            <ReliabilityPanel briefing={briefing} />
          </div>
        )}
      </main>
    </div>
  );
}
