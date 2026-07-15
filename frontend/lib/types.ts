// Types matching backend Pydantic schemas exactly

export type RunStatus =
  | "running"
  | "completed"
  | "failed"
  | "published"
  | "pending_review"
  | "rejected";

export type TriggeredBy = "manual" | "scheduled";

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
  triggered_by: TriggeredBy;
}

export interface Briefing {
  metadata: RunMetadata;
  sections: Section[];
  unverified_flags: string[];
}

// Lightweight summary from GET /api/runs
export interface RunSummary {
  run_id: string;
  topic: string;
  started_at: string;
  status: RunStatus;
  sources_used: number;
  sources_skipped_count: number;
  triggered_by: TriggeredBy;
}

// KPI data from GET /api/kpis
export interface KpiData {
  run_success_rate: number;    // 0-100 %
  citation_rate: number;       // 0-100 % of claims with citations
  source_coverage: number;     // avg sources used per run
  avg_duration_seconds: number;
  publish_rate: number;        // 0-100 % of reviewed runs published
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  published_runs: number;
}
