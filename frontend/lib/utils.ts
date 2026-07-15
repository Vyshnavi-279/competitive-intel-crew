import type { RunStatus } from "./types";

/** Format a duration in seconds to a human-readable string */
export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

/** Relative timestamp: "2 mins ago", "3 hrs ago", etc. */
export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

/** Map status → clay CSS class for the raised surface */
export function statusToClaySurface(status: RunStatus): string {
  switch (status) {
    case "running":       return "clay-raised--running";
    case "published":     return "clay-raised--published";
    case "pending_review":return "clay-raised--pending";
    case "rejected":      return "clay-raised--rejected";
    default:              return "clay-raised"; // failed / completed
  }
}

/** Map status → color hex for dots / badges */
export function statusToColor(status: RunStatus): string {
  switch (status) {
    case "running":        return "#93B6C4";
    case "published":      return "#A9C6AE";
    case "pending_review": return "#E8C4A2";
    case "rejected":       return "#C98B7A";
    default:               return "#8C8474";
  }
}

/** Human-readable label for a status */
export function statusLabel(status: RunStatus): string {
  switch (status) {
    case "running":        return "Running";
    case "published":      return "Published";
    case "pending_review": return "Pending Review";
    case "rejected":       return "Rejected";
    case "completed":      return "Completed";
    case "failed":         return "Failed";
    default:               return status;
  }
}

/** Whether a run is still actively running (requires polling) */
export function isRunning(status: RunStatus): boolean {
  return status === "running";
}
