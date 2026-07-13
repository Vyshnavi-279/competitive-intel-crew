// app/lib/types.ts
// TypeScript types mirroring the backend Pydantic models in backend/models/schemas.py

export interface Citation {
  source_name: string;
  url: string | null;
}

export interface Claim {
  text: string;
  citations: Citation[];
  verified: boolean;
}

export interface Section {
  title: "Executive Summary" | "Competitor Pricing & Product Moves" | "Market Signals";
  claims: Claim[];
}

export type RunStatus =
  | "running"
  | "completed"
  | "failed"
  | "published"
  | "pending_review";

export interface RunMetadata {
  run_id: string;
  topic: string;
  started_at: string; // ISO-8601
  duration_seconds: number | null;
  sources_attempted: number;
  sources_used: number;
  sources_skipped: string[];
  total_steps: number;
  token_estimate: number | null;
  status: RunStatus;
}

export interface Briefing {
  metadata: RunMetadata;
  sections: Section[];
  unverified_flags: string[];
}

// Lightweight shape returned by GET /api/runs (no briefing_json blob)
export interface RunSummary {
  run_id: string;
  topic: string;
  started_at: string;
  status: RunStatus;
  sources_used: number;
  sources_skipped_count: number;
}

// Agent names as a tuple for iteration
export const AGENT_NAMES = ["Coordinator", "Researcher", "Analyst", "Writer"] as const;
export type AgentName = (typeof AGENT_NAMES)[number];

// Per-agent status used in the sidebar
export type AgentStatus = "idle" | "running" | "done" | "error";
export type AgentStatusMap = Record<AgentName, AgentStatus>;
