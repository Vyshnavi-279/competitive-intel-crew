import { ExternalLink } from "lucide-react";
import type { Citation } from "@/lib/types";

interface CitationChipProps {
  citation: Citation;
}

export function CitationChip({ citation }: CitationChipProps) {
  const hasUrl = !!citation.url && citation.url.startsWith("http");

  const chipContent = (
    <span
      className="inline-flex items-center gap-1.5 clay-inset-pill px-2.5 py-1 text-[13px] font-medium transition-all duration-150 hover:brightness-95 active:scale-95"
      title={hasUrl ? citation.url! : citation.source_name}
    >
      <span style={{ color: "#2E2A22" }}>{citation.source_name}</span>
      {hasUrl && (
        <span
          className="clay-knob flex items-center justify-center w-4 h-4 shrink-0 rounded-full"
          aria-hidden="true"
          style={{ background: "rgba(147,182,196,0.35)" }}
        >
          <ExternalLink size={9} strokeWidth={2.5} color="#2E5E36" />
        </span>
      )}
    </span>
  );

  if (hasUrl) {
    return (
      <a
        href={citation.url!}
        target="_blank"
        rel="noopener noreferrer"
        title={`Open source: ${citation.url}`}
        className="inline-flex cursor-pointer"
        aria-label={`Open ${citation.source_name} in a new tab`}
      >
        {chipContent}
      </a>
    );
  }

  // No URL — render as non-clickable chip
  return (
    <span className="inline-flex cursor-default" aria-label={citation.source_name}>
      {chipContent}
    </span>
  );
}
