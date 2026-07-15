import { RunMonitor } from "@/components/RunMonitor";
import { BriefingDetail } from "@/components/BriefingDetail";
import { getRun } from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function RunPage({ params }: PageProps) {
  const { id } = await params;

  let briefing = null;
  try {
    briefing = await getRun(id);
  } catch {
    // briefing stays null — RunMonitor handles graceful loading
  }

  // If running or not yet loaded, show the live monitor.
  // Pass the initial briefing data down to avoid RunMonitor doing a redundant
  // fetch on mount (which would also cause a brief flash and a race condition).
  if (!briefing || briefing.metadata.status === "running") {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="mb-6">
          <p className="eyebrow mb-1">Live Monitor</p>
          <h1
            className="text-2xl font-semibold"
            style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
          >
            {briefing?.metadata.topic ?? "Loading…"}
          </h1>
        </div>
        <RunMonitor runId={id} initialBriefing={briefing} />
      </div>
    );
  }

  // Otherwise show the full briefing detail
  return (
    <div className="max-w-2xl mx-auto">
      <BriefingDetail briefing={briefing} />
    </div>
  );
}
