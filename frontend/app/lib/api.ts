// app/lib/api.ts
// All communication with the FastAPI backend lives here.
// Components import these functions instead of calling fetch() inline.

import type { Briefing, RunSummary } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Internal helper — wraps fetch with consistent error handling
// ---------------------------------------------------------------------------

async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${init?.method ?? "GET"} ${path} → ${res.status}: ${body}`);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API helpers
// ---------------------------------------------------------------------------

/**
 * GET /api/runs
 * Returns the most recent run summaries for the history sidebar.
 */
export async function getRuns(limit = 20): Promise<RunSummary[]> {
  return apiFetch<RunSummary[]>(`/api/runs?limit=${limit}`);
}

/**
 * GET /api/runs/:runId
 * Returns the full Briefing for a specific run (used when clicking a history item).
 */
export async function getRun(runId: string): Promise<Briefing> {
  return apiFetch<Briefing>(`/api/runs/${encodeURIComponent(runId)}`);
}

/**
 * POST /api/run
 * Kicks off a new crew run for the given topic and streams back the full
 * Briefing once the crew completes. This is a long-running call (~30–120s).
 */
export async function runBriefing(topic: string): Promise<Briefing> {
  return apiFetch<Briefing>("/api/run", {
    method: "POST",
    body: JSON.stringify({ topic }),
  });
}

/**
 * POST /api/runs/:runId/publish
 * Transitions a pending_review run to published.
 */
export async function publishRun(
  runId: string
): Promise<{ run_id: string; status: string; message: string }> {
  return apiFetch(`/api/runs/${encodeURIComponent(runId)}/publish`, {
    method: "POST",
  });
}

/**
 * GET /api/health
 * Liveness check — useful to show a backend-connected indicator in the UI.
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const data = await apiFetch<{ status: string }>("/api/health");
    return data.status === "ok";
  } catch {
    return false;
  }
}
