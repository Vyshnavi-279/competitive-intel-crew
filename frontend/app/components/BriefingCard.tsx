"use client";

// app/components/BriefingCard.tsx
// Renders one section of a competitive-intel briefing.
//
// Layout:
//   ┌─────────────────────────────────────────────┐
//   │  SECTION TITLE                [claim count]  │
//   │─────────────────────────────────────────────│
//   │  • Claim text …                              │
//   │    [Reuters] [Bloomberg]    ← citation chips │
//   │                                              │
//   │  • ⚠ Claim text …           ← Unverified     │
//   │    [GossipBlog]                              │
//   └─────────────────────────────────────────────┘
//
// Citation chips are clickable links that open the source URL in a new tab.
// Claims that start with "Unverified:" render with an amber warning badge.

import { AlertTriangle, CheckCircle, ExternalLink } from "lucide-react";
import type { Claim, Citation, Section } from "@/app/lib/types";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CitationChip({ citation }: { citation: Citation }) {
  const inner = (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-[#0e3a5c] text-teal-300 border border-teal-700/50 hover:border-teal-400 hover:text-teal-200 transition-colors">
      {citation.source_name}
      {citation.url && <ExternalLink className="w-2.5 h-2.5 opacity-70" />}
    </span>
  );

  if (citation.url) {
    return (
      <a
        href={citation.url}
        target="_blank"
        rel="noopener noreferrer"
        title={`Open source: ${citation.source_name}`}
      >
        {inner}
      </a>
    );
  }
  return inner;
}

function ClaimRow({ claim }: { claim: Claim }) {
  const isUnverified = claim.text.startsWith("Unverified:") || !claim.verified;
  const displayText = claim.text.startsWith("Unverified:")
    ? claim.text.slice("Unverified:".length).trim()
    : claim.text;

  return (
    <li className="group flex flex-col gap-1.5 py-3 border-b border-[#1e3a54]/60 last:border-0">
      {/* Claim text row */}
      <div className="flex items-start gap-2">
        {isUnverified ? (
          <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />
        ) : (
          <CheckCircle className="w-4 h-4 text-teal-400 mt-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
        )}
        <div className="flex-1 min-w-0">
          <p className={`text-sm leading-relaxed ${isUnverified ? "text-amber-100/80" : "text-slate-200"}`}>
            {isUnverified && (
              <span className="inline-flex items-center gap-1 mr-2 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide bg-amber-500/20 text-amber-400 border border-amber-500/40">
                <AlertTriangle className="w-2.5 h-2.5" />
                Unverified
              </span>
            )}
            {displayText}
          </p>

          {/* Citation chips */}
          {claim.citations.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {claim.citations.map((c, i) => (
                <CitationChip key={`${c.source_name}-${i}`} citation={c} />
              ))}
            </div>
          )}

          {/* No citations warning */}
          {claim.citations.length === 0 && (
            <span className="inline-block mt-1.5 text-[10px] text-red-400/70 uppercase tracking-wide">
              No citations attached
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// BriefingCard
// ---------------------------------------------------------------------------

interface BriefingCardProps {
  section: Section;
  /** Highlight the card with a teal left-border accent (used for Executive Summary) */
  featured?: boolean;
  className?: string;
}

export default function BriefingCard({
  section,
  featured = false,
  className = "",
}: BriefingCardProps) {
  const unverifiedCount = section.claims.filter(
    (c) => c.text.startsWith("Unverified:") || !c.verified
  ).length;

  const citedCount = section.claims.filter((c) => c.citations.length > 0).length;

  return (
    <article
      className={`
        rounded-xl border bg-[#0d1f35] overflow-hidden
        ${featured
          ? "border-teal-600/60 shadow-[0_0_0_1px_rgba(20,184,166,0.15),0_4px_24px_rgba(0,0,0,0.4)]"
          : "border-[#1e3a54] shadow-[0_2px_12px_rgba(0,0,0,0.3)]"
        }
        ${className}
      `}
    >
      {/* Card header */}
      <div
        className={`
          flex items-center justify-between px-5 py-3.5
          ${featured
            ? "bg-gradient-to-r from-teal-900/50 to-[#0d1f35] border-b border-teal-700/40"
            : "bg-[#0a1929] border-b border-[#1e3a54]"
          }
        `}
      >
        <div className="flex items-center gap-3">
          {featured && (
            <span className="w-1.5 h-6 rounded-full bg-teal-400 flex-shrink-0" />
          )}
          <h2
            className={`font-semibold tracking-tight ${
              featured ? "text-teal-300 text-base" : "text-slate-300 text-sm"
            }`}
          >
            {section.title}
          </h2>
          {featured && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-teal-500/20 text-teal-400 border border-teal-500/30">
              Recommendation
            </span>
          )}
        </div>

        {/* Stats */}
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>{section.claims.length} claim{section.claims.length !== 1 ? "s" : ""}</span>
          <span className="text-teal-600">·</span>
          <span className={citedCount < section.claims.length ? "text-amber-500" : "text-teal-500"}>
            {citedCount}/{section.claims.length} cited
          </span>
          {unverifiedCount > 0 && (
            <>
              <span className="text-teal-600">·</span>
              <span className="text-amber-400 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                {unverifiedCount} unverified
              </span>
            </>
          )}
        </div>
      </div>

      {/* Claims list */}
      <div className="px-5">
        {section.claims.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500 italic">
            No claims in this section.
          </p>
        ) : (
          <ul className="divide-y-0">
            {section.claims.map((claim, i) => (
              <ClaimRow key={i} claim={claim} />
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
