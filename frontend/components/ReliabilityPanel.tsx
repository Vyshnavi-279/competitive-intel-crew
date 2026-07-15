import { AlertTriangle } from "lucide-react";

interface ReliabilityPanelProps {
  sourcesUsed: number;
  sourcesAttempted: number;
  sourcesSkipped: string[];
  droppedCount: number;
  unverifiedCount: number;
}

function CircleDial({ used, attempted }: { used: number; attempted: number }) {
  const size = 72;
  const r = 28;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const pct = attempted > 0 ? used / attempted : 0;
  const dash = pct * circ;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      {/* Track */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none"
        stroke="#EFE6D8"
        strokeWidth="8"
        style={{ filter: "drop-shadow(inset 2px 2px 4px rgba(74,68,56,0.15))" }}
      />
      {/* Fill */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none"
        stroke="#A9C6AE"
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circ}`}
        strokeDashoffset={circ / 4} // start from top
        style={{ transition: "stroke-dasharray 0.6s ease" }}
      />
      {/* Center text */}
      <text
        x={cx} y={cy - 4}
        textAnchor="middle"
        fontSize="13"
        fontWeight="700"
        fill="#4A4438"
        fontFamily="var(--font-inter), Inter, sans-serif"
      >
        {used}
      </text>
      <text
        x={cx} y={cy + 10}
        textAnchor="middle"
        fontSize="9"
        fill="#8C8474"
        fontFamily="var(--font-inter), Inter, sans-serif"
      >
        /{attempted}
      </text>
    </svg>
  );
}

export function ReliabilityPanel({
  sourcesUsed,
  sourcesAttempted,
  sourcesSkipped,
  droppedCount,
  unverifiedCount,
}: ReliabilityPanelProps) {
  return (
    <div className="clay-raised p-5">
      <p className="eyebrow mb-3">Source Reliability</p>

      <div className="flex items-center gap-5">
        {/* Dial */}
        <div className="shrink-0">
          <CircleDial used={sourcesUsed} attempted={sourcesAttempted} />
          <p className="text-[10px] text-center mt-1" style={{ color: "#8C8474" }}>
            sources used
          </p>
        </div>

        {/* Stats */}
        <div className="flex flex-col gap-2 flex-1">
          <Stat label="Used" value={sourcesUsed} color="#A9C6AE" />
          <Stat label="Skipped" value={sourcesAttempted - sourcesUsed} color="#C98B7A" />
          <Stat label="Unverified claims" value={unverifiedCount} color="#E8C4A2" />
          <Stat label="Dropped claims" value={droppedCount} color="#C98B7A" />
        </div>
      </div>

      {/* Skipped sources list */}
      {sourcesSkipped.length > 0 && (
        <div className="mt-4">
          <p className="eyebrow mb-2">Skipped Sources</p>
          <div className="flex flex-wrap gap-2 overflow-x-auto">
            {sourcesSkipped.map((src, i) => (
              <span
                key={i}
                className="clay-inset-pill inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px]"
                style={{ color: "#C98B7A" }}
              >
                <AlertTriangle size={10} strokeWidth={2.5} />
                <span className="truncate max-w-[180px]">{src}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span style={{ color: "#8C8474" }}>{label}</span>
      <span
        className="font-tabular font-semibold px-2 py-0.5 rounded-full text-[11px]"
        style={{ background: `${color}33`, color }}
      >
        {value}
      </span>
    </div>
  );
}
