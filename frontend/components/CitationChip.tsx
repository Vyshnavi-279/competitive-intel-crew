import { ExternalLink } from "lucide-react";
import type { Citation } from "@/lib/types";

interface CitationChipProps {
  citation: Citation;
}

export function CitationChip({ citation }: CitationChipProps) {
  const inner = (
    <span className="inline-flex items-center gap-1 clay-inset-pill px-2.5 py-1 text-[11px] font-medium transition-all duration-150 hover:brightness-95">
      <span style={{ color: "#8C8474" }}>{citation.source_name}</span>
      {citation.url && (
        <span
          className="clay-knob flex items-center justify-center w-4 h-4 shrink-0"
          aria-hidden="true"
        >
          <ExternalLink size={9} strokeWidth={2.5} color="#8C8474" />
        </span>
      )}
    </span>
  );

  if (citation.url) {
    return (
      <a
        href={citation.url}
        target="_blank"
        rel="noopener noreferrer"
        title={`Open ${citation.source_name}`}
        className="inline-flex"
      >
        {inner}
      </a>
    );
  }

  return <span className="inline-flex">{inner}</span>;
}
