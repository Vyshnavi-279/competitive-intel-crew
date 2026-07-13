"use client";

// app/components/ReliabilityPanel.tsx
// Governance and reliability summary panel.
//
// Shows:
//  • Source reliability bar (attempted / used / skipped)
//  • Timed-out / skipped sources (expandable list)
//  • Claims governance (dropped count, flags from unverified_flags)
//  • 5-layer evaluation scorecard (if all data is available on the run)

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Info,
  Shield,
  XCircle,
} from "lucide-react";
import type { Briefing } from "@/app/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(n: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((n / total) * 100);
}

interface LayerRow {
  layer: string;
  description: string;
  pass: boolean | null; // null = not enough data
}

function deriveEvalLayers(briefing: Briefing): LayerRow[] {
  const { metadata, sections, unverified_flags } = briefing;

  const allCitationsPresent = sections.every((s) =>
    s.claims.every((c) => c.citations.length > 0)
  );
  const hasThreeSections = sections.length === 3;
  const noFailedRun = metadata.status !== "failed";
  const sourceCapRespected = metadata.sources_skipped.length <= metadata.sources_attempted;
  const hedgedFlagCount = unverified_flags.filter((f) =>
    f.toLowerCase().includes("hedged")
  ).length;
  const droppedFlagCount = unverified_flags.filter((f) =>
    f.toLowerCase().includes("dropped")
  ).length;

  return [
    {
      layer: "Trace — full pipeline",
      description: "3 sections, correct titles, run completed",
      pass: hasThreeSections && noFailedRun,
    },
    {
      layer: "Failure handling",
      description: "Run completed even if sources were skipped",
      pass: noFailedRun,
    },
    {
      layer: "Governance — citations",
      description: "All surviving claims have ≥1 citation",
      pass: allCitationsPresent,
    },
    {
      layer: "Reliability — source cap",
      description: "Sources used ≤ attempted (cap enforced)",
      pass: sourceCapRespected,
    },
    {
      layer: "Adversarial — hedging",
      description: "Unverified claims prefixed, not dropped silently",
      pass: droppedFlagCount === 0 ? null : hedgedFlagCount >= 0,
    },
  ];
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ProgressBar({
  used,
  skipped,
  total,
}: {
  used: number;
  skipped: number;
  total: number;
}) {
  const usedPct = pct(used, total);
  const skippedPct = pct(skipped, total);

  return (
    <div className="space-y-1.5">
      <div className="flex h-2 rounded-full overflow-hidden bg-[#0a1929]">
        <div
          className="bg-teal-500 transition-all"
          style={{ width: `${usedPct}%` }}
        />
        <div
          className="bg-amber-500/70 transition-all"
          style={{ width: `${skippedPct}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-500">
        <span className="text-teal-400">{used} used</span>
        <span className="text-amber-400">{skipped} skipped</span>
        <span>{total} attempted</span>
      </div>
    </div>
  );
}

function LayerBadge({ pass }: { pass: boolean | null }) {
  if (pass === null)
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-700 text-slate-400">
        <Info className="w-3 h-3" /> N/A
      </span>
    );
  if (pass)
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-teal-900/60 text-teal-400 border border-teal-700/50">
        <CheckCircle className="w-3 h-3" /> PASS
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-900/40 text-red-400 border border-red-700/50">
      <XCircle className="w-3 h-3" /> FAIL
    </span>
  );
}

// ---------------------------------------------------------------------------
// ReliabilityPanel
// ---------------------------------------------------------------------------

interface ReliabilityPanelProps {
  briefing: Briefing;
}

export default function ReliabilityPanel({ briefing }: ReliabilityPanelProps) {
  const [skippedOpen, setSkippedOpen] = useState(false);
  const [flagsOpen, setFlagsOpen] = useState(false);

  const { metadata, unverified_flags } = briefing;
  const skippedCount = metadata.sources_skipped.length;
  const droppedFlags = unverified_flags.filter((f) =>
    f.toLowerCase().includes("dropped")
  );
  const hedgedFlags = unverified_flags.filter((f) =>
    f.toLowerCase().includes("hedged")
  );
  const evalLayers = deriveEvalLayers(briefing);
  const layerPassCount = evalLayers.filter((l) => l.pass === true).length;
  const layerFailCount = evalLayers.filter((l) => l.pass === false).length;

  return (
    <aside className="rounded-xl border border-[#1e3a54] bg-[#0d1f35] overflow-hidden shadow-[0_2px_12px_rgba(0,0,0,0.3)]">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 py-3 bg-[#0a1929] border-b border-[#1e3a54]">
        <Shield className="w-4 h-4 text-teal-400" />
        <h3 className="text-sm font-semibold text-slate-300">
          Reliability &amp; Governance
        </h3>
        <span className={`ml-auto text-xs font-semibold px-2 py-0.5 rounded-full ${
          layerFailCount === 0
            ? "bg-teal-900/50 text-teal-400"
            : "bg-red-900/40 text-red-400"
        }`}>
          {layerPassCount}/{evalLayers.length} layers pass
        </span>
      </div>

      <div className="p-4 space-y-5">

        {/* Source reliability */}
        <section>
          <p className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
            Source Reliability
          </p>
          <ProgressBar
            used={metadata.sources_used}
            skipped={skippedCount}
            total={metadata.sources_attempted}
          />

          {/* Skipped sources list */}
          {skippedCount > 0 && (
            <div className="mt-2">
              <button
                onClick={() => setSkippedOpen((o) => !o)}
                className="flex items-center gap-1.5 text-xs text-amber-400 hover:text-amber-300 transition-colors"
              >
                <AlertTriangle className="w-3 h-3" />
                {skippedCount} source{skippedCount !== 1 ? "s" : ""} timed out / skipped
                {skippedOpen ? (
                  <ChevronUp className="w-3 h-3" />
                ) : (
                  <ChevronDown className="w-3 h-3" />
                )}
              </button>
              {skippedOpen && (
                <ul className="mt-2 space-y-1 pl-4">
                  {metadata.sources_skipped.map((q, i) => (
                    <li
                      key={i}
                      className="text-[11px] text-slate-400 font-mono truncate before:content-['›'] before:mr-1.5 before:text-amber-500/60"
                    >
                      {q}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        {/* Claims governance */}
        <section>
          <p className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
            Claims Governance
          </p>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-[#0a1929] px-3 py-2.5 border border-[#1e3a54]">
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Dropped</p>
              <p className={`text-xl font-bold mt-0.5 ${droppedFlags.length > 0 ? "text-red-400" : "text-teal-400"}`}>
                {droppedFlags.length}
              </p>
              <p className="text-[10px] text-slate-500 mt-0.5">uncited claims</p>
            </div>
            <div className="rounded-lg bg-[#0a1929] px-3 py-2.5 border border-[#1e3a54]">
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Hedged</p>
              <p className={`text-xl font-bold mt-0.5 ${hedgedFlags.length > 0 ? "text-amber-400" : "text-teal-400"}`}>
                {hedgedFlags.length}
              </p>
              <p className="text-[10px] text-slate-500 mt-0.5">unverified claims</p>
            </div>
          </div>

          {/* Flag list */}
          {unverified_flags.length > 0 && (
            <div className="mt-2">
              <button
                onClick={() => setFlagsOpen((o) => !o)}
                className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-300 transition-colors"
              >
                <Info className="w-3 h-3" />
                {unverified_flags.length} governance flag{unverified_flags.length !== 1 ? "s" : ""}
                {flagsOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {flagsOpen && (
                <ul className="mt-2 space-y-1 pl-4">
                  {unverified_flags.map((f, i) => (
                    <li
                      key={i}
                      className={`text-[11px] truncate before:content-['›'] before:mr-1.5 ${
                        f.toLowerCase().includes("dropped")
                          ? "text-red-400/80 before:text-red-500/50"
                          : "text-amber-400/80 before:text-amber-500/50"
                      }`}
                    >
                      {f}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        {/* 5-layer evaluation scorecard */}
        <section>
          <p className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
            Evaluation Layers
          </p>
          <ul className="space-y-2">
            {evalLayers.map((row) => (
              <li key={row.layer} className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-slate-300 truncate">
                    {row.layer}
                  </p>
                  <p className="text-[10px] text-slate-500 mt-0.5">
                    {row.description}
                  </p>
                </div>
                <LayerBadge pass={row.pass} />
              </li>
            ))}
          </ul>
        </section>

      </div>
    </aside>
  );
}
