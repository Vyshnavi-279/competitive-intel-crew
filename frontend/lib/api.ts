import type { Briefing, RunSummary } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

/** POST /api/run — trigger a new briefing run */
export async function triggerRun(topic: string): Promise<Briefing> {
  return apiFetch<Briefing>("/api/run", {
    method: "POST",
    body: JSON.stringify({ topic }),
  });
}

/** GET /api/runs — list recent run summaries */
export async function listRuns(limit = 50): Promise<RunSummary[]> {
  return apiFetch<RunSummary[]>(`/api/runs?limit=${limit}`);
}

/** GET /api/runs/{id} — full briefing */
export async function getRun(runId: string): Promise<Briefing> {
  return apiFetch<Briefing>(`/api/runs/${runId}`);
}

/** POST /api/runs/{id}/publish */
export async function publishRun(
  runId: string
): Promise<{ run_id: string; status: string; message: string }> {
  return apiFetch(`/api/runs/${runId}/publish`, { method: "POST" });
}

/** POST /api/runs/{id}/reject */
export async function rejectRun(
  runId: string,
  reason?: string
): Promise<{ run_id: string; status: string; reason: string | null; message: string }> {
  return apiFetch(`/api/runs/${runId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

/** GET /api/health */
export async function getHealth(): Promise<{ status: string }> {
  return apiFetch("/api/health");
}
