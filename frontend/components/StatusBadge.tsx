import type { RunStatus } from "@/lib/types";
import { statusLabel, statusToColor } from "@/lib/utils";

interface StatusBadgeProps {
  status: RunStatus;
  size?: "sm" | "md";
}

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const color = statusToColor(status);
  const label = statusLabel(status);

  const px = size === "sm" ? "px-2.5 py-0.5" : "px-3 py-1";
  const text = size === "sm" ? "text-[10px]" : "text-[11px]";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-semibold rounded-full tracking-wide ${px} ${text}`}
      style={{
        background: `${color}33`,
        color: color,
        boxShadow: `inset 2px 2px 4px rgba(0,0,0,0.06), inset -2px -2px 4px rgba(255,255,255,0.5)`,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: color }}
        aria-hidden="true"
      />
      {label.toUpperCase()}
    </span>
  );
}
