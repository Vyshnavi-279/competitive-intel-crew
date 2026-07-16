import type { Briefing, KpiData, RunSummary } from "./types";

// In production (Render) NEXT_PUBLIC_API_URL is injected at build time.
// In local dev it is not set, so fall back to the local backend.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? "https://competitive-intel-crew-2.onrender.com"
    : "http://localhost:8000");

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

/** GET /api/kpis — five business KPIs computed from all stored runs */
export async function fetchKpis(): Promise<KpiData> {
  return apiFetch<KpiData>("/api/kpis");
}

/** DELETE /api/runs/{id} — delete a single run */
export async function deleteRun(
  runId: string
): Promise<{ deleted: string; message: string }> {
  return apiFetch(`/api/runs/${runId}`, { method: "DELETE" });
}

/** DELETE /api/runs/failed — bulk-delete all failed runs */
export async function deleteAllFailed(): Promise<{ deleted: number; message: string }> {
  return apiFetch("/api/runs/failed", { method: "DELETE" });
}
