"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Calendar, MousePointer, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import type { Briefing, Section, Claim } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { CitationChip } from "@/components/CitationChip";
import { ReliabilityPanel } from "@/components/ReliabilityPanel";
import { AgentChain, buildAgentNodes } from "@/components/AgentChain";
import { formatDuration, timeAgo } from "@/lib/utils";
import { publishRun, rejectRun } from "@/lib/api";

interface BriefingDetailProps {
  briefing: Briefing;
}

function ClaimRow({ claim }: { claim: Claim }) {
  const isUnverified = !claim.verified || claim.text.startsWith("Unverified:");
  const text = claim.text.replace(/^Unverified:\s*/i, "");

  if (isUnverified) {
    return (
      <div className="clay-unverified p-3 flex flex-col gap-2">
        <p className="eyebrow" style={{ color: "#b5743a" }}>Unverified</p>
        <p className="text-sm leading-relaxed" style={{ color: "#4A4438" }}>{text}</p>
        {claim.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {claim.citations.map((c, i) => <CitationChip key={i} citation={c} />)}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 py-2.5 border-b border-[#EFE6D8] last:border-0">
      <p className="text-sm leading-relaxed" style={{ color: "#4A4438" }}>{text}</p>
      {claim.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {claim.citations.map((c, i) => <CitationChip key={i} citation={c} />)}
        </div>
      )}
    </div>
  );
}

function SectionCard({ section }: { section: Section }) {
  return (
    <div className="clay-raised p-6">
      <h3
        className="text-base font-semibold mb-4"
        style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#4A4438" }}
      >
        {section.title}
      </h3>
      {section.claims.length === 0 ? (
        <p className="text-sm" style={{ color: "#8C8474" }}>No claims in this section.</p>
      ) : (
        <div className="flex flex-col gap-1">
          {section.claims.map((claim, i) => (
            <ClaimRow key={i} claim={claim} />
          ))}
        </div>
      )}
    </div>
  );
}

export function BriefingDetail({ briefing }: BriefingDetailProps) {
  const router = useRouter();
  const [actionLoading, setActionLoading] = useState<"publish" | "reject" | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const m = briefing.metadata;
  const isPendingReview = m.status === "pending_review";

  // Reliability stats
  const unverifiedCount = briefing.unverified_flags.filter(f => f.toLowerCase().includes("unverified") || f.toLowerCase().includes("hedged")).length;
  const droppedCount = briefing.unverified_flags.filter(f => f.toLowerCase().includes("dropped")).length;

  async function handlePublish() {
    setActionLoading("publish");
    setActionError(null);
    try {
      await publishRun(m.run_id);
      router.refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to publish");
      setActionLoading(null);
    }
  }

  async function handleReject() {
    setActionLoading("reject");
    setActionError(null);
    try {
      await rejectRun(m.run_id, rejectReason.trim() || undefined);
      router.refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to reject");
      setActionLoading(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Run meta header */}
      <div className="clay-raised p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap mb-3">
          <div className="flex-1">
            <p className="eyebrow mb-1">Briefing</p>
            <h1
              className="text-xl font-semibold leading-snug"
              style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#4A4438" }}
            >
              {m.topic}
            </h1>
          </div>
          <StatusBadge status={m.status} />
        </div>

        <div className="flex flex-wrap items-center gap-3 mt-2">
          {/* Triggered by */}
          <span
            className="clay-inset-pill inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px]"
            style={{ color: "#8C8474" }}
          >
            {m.triggered_by === "scheduled"
              ? <><Calendar size={11} strokeWidth={2} /> Scheduled</>
              : <><MousePointer size={11} strokeWidth={2} /> Manual</>
            }
          </span>

          {/* Timestamp */}
          <span className="text-xs" style={{ color: "#8C8474" }}>
            {timeAgo(m.started_at)}
            {m.duration_seconds != null && ` · ${formatDuration(m.duration_seconds)}`}
          </span>

          {/* Source count */}
          {m.sources_used > 0 && (
            <span className="text-xs font-tabular" style={{ color: "#8C8474" }}>
              {m.sources_used} sources used
            </span>
          )}
        </div>
      </div>

      {/* Agent chain (collapsed / done state) */}
      <div className="clay-raised p-5">
        <p className="eyebrow mb-4">Agent Pipeline</p>
        <AgentChain agents={buildAgentNodes(m.status, m.sources_used)} />
      </div>

      {/* Sections */}
      {briefing.sections.length === 0 ? (
        <div className="clay-raised p-8 text-center">
          <p className="text-sm" style={{ color: "#8C8474" }}>
            No sections were parsed from this run's output.
          </p>
          {briefing.unverified_flags.length > 0 && (
            <div className="mt-4 text-left">
              {briefing.unverified_flags.map((f, i) => (
                <p key={i} className="text-xs mt-1" style={{ color: "#C98B7A" }}>{f}</p>
              ))}
            </div>
          )}
        </div>
      ) : (
        briefing.sections.map((s, i) => <SectionCard key={i} section={s} />)
      )}

      {/* Reliability panel */}
      <ReliabilityPanel
        sourcesUsed={m.sources_used}
        sourcesAttempted={m.sources_attempted}
        sourcesSkipped={m.sources_skipped ?? []}
        droppedCount={droppedCount}
        unverifiedCount={unverifiedCount}
      />

      {/* Action bar — only in pending_review */}
      {isPendingReview && (
        <div className="clay-raised p-5 flex flex-col gap-4">
          <p className="eyebrow">Human Review</p>
          <p className="text-xs" style={{ color: "#8C8474" }}>
            Review the briefing above before it reaches the strategy org. Approve to publish or reject with an optional reason.
          </p>

          {actionError && (
            <p className="text-xs" style={{ color: "#C98B7A" }}>⚠ {actionError}</p>
          )}

          {/* Reject form */}
          {showRejectForm && (
            <div className="clay-inset rounded-[20px] p-4 flex flex-col gap-3">
              <label className="eyebrow">Rejection reason (optional)</label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="e.g. Insufficient sourcing on Section 2"
                rows={3}
                className="bg-transparent text-sm resize-none outline-none placeholder:text-[#8C8474]"
                style={{ color: "#4A4438" }}
              />
            </div>
          )}

          <div className="flex gap-3 flex-wrap">
            {/* Approve */}
            <button
              onClick={handlePublish}
              disabled={actionLoading !== null}
              className="clay-knob--done flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-full disabled:opacity-50 disabled:cursor-not-allowed hover:brightness-95 active:scale-95 transition-all"
              style={{ color: "#2e5e36", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
            >
              {actionLoading === "publish"
                ? <span className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
                : <CheckCircle2 size={15} strokeWidth={2.5} />
              }
              Approve &amp; Publish
            </button>

            {/* Reject */}
            {!showRejectForm ? (
              <button
                onClick={() => setShowRejectForm(true)}
                disabled={actionLoading !== null}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-full disabled:opacity-50 hover:brightness-95 active:scale-95 transition-all"
                style={{
                  color: "#7a3b2e",
                  background: "#edd8d2",
                  boxShadow: "4px 4px 8px rgba(74,68,56,0.18), -3px -3px 6px rgba(255,255,255,0.7)",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                }}
              >
                <XCircle size={15} strokeWidth={2.5} />
                Reject
              </button>
            ) : (
              <button
                onClick={handleReject}
                disabled={actionLoading !== null}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-full disabled:opacity-50 hover:brightness-95 active:scale-95 transition-all"
                style={{
                  color: "#7a3b2e",
                  background: "#edd8d2",
                  boxShadow: "4px 4px 8px rgba(74,68,56,0.18), -3px -3px 6px rgba(255,255,255,0.7)",
                  fontFamily: "var(--font-poppins), Poppins, sans-serif",
                }}
              >
                {actionLoading === "reject"
                  ? <span className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
                  : <XCircle size={15} strokeWidth={2.5} />
                }
                Confirm Reject
              </button>
            )}
          </div>
        </div>
      )}

      {/* Governance flags */}
      {briefing.unverified_flags.length > 0 && !isPendingReview && (
        <div className="clay-inset rounded-[20px] p-4">
          <p className="eyebrow mb-2">Governance Log</p>
          <ul className="flex flex-col gap-1">
            {briefing.unverified_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs" style={{ color: "#8C8474" }}>
                <AlertTriangle size={11} className="shrink-0 mt-0.5" style={{ color: "#E8C4A2" }} />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
