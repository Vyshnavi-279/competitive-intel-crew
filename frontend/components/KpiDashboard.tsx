"use client";

import type { KpiData } from "@/lib/types";
import { formatDuration } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, BookOpen, Clock, TrendingUp } from "lucide-react";

interface KpiCardProps {
  icon: React.ElementType;
  label: string;
  value: string;
  sub: string;
  /** 0-100 fill for the arc indicator */
  pct?: number;
  color: string;
}

function KpiCard({ icon: Icon, label, value, sub, pct, color }: KpiCardProps) {
  // Small arc SVG (180° half-circle gauge)
  const r = 26;
  const circ = Math.PI * r; // half circumference
  const fill = pct != null ? (pct / 100) * circ : 0;

  return (
    <div className="clay-raised p-5 flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-center gap-2">
        <span
          className="clay-knob flex items-center justify-center w-8 h-8 shrink-0"
          aria-hidden="true"
        >
          <Icon size={14} strokeWidth={2} color="#4A4438" />
        </span>
        <p className="eyebrow leading-tight">{label}</p>
      </div>

      {/* Value + optional gauge */}
      <div className="flex items-end justify-between gap-2">
        <div>
          <p
            className="text-3xl font-bold leading-none"
            style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
          >
            {value}
          </p>
          <p className="text-[13px] mt-1" style={{ color: "#2E2A22" }}>{sub}</p>
        </div>

        {pct != null && (
          <svg
            width="60"
            height="34"
            viewBox="0 0 60 34"
            aria-label={`${Math.round(pct)}%`}
            className="shrink-0"
          >
            {/* Track */}
            <path
              d="M 4 30 A 26 26 0 0 1 56 30"
              fill="none"
              stroke="#EFE6D8"
              strokeWidth="7"
              strokeLinecap="round"
            />
            {/* Fill */}
            <path
              d="M 4 30 A 26 26 0 0 1 56 30"
              fill="none"
              stroke={color}
              strokeWidth="7"
              strokeLinecap="round"
              strokeDasharray={`${fill} ${circ}`}
              style={{ transition: "stroke-dasharray 0.6s ease" }}
            />
          </svg>
        )}
      </div>
    </div>
  );
}

interface KpiDashboardProps {
  kpis: KpiData;
}

export function KpiDashboard({ kpis }: KpiDashboardProps) {
  const cards: KpiCardProps[] = [
    {
      icon: CheckCircle2,
      label: "Run Success Rate",
      value: `${kpis.run_success_rate}%`,
      sub: `${kpis.successful_runs} of ${kpis.total_runs} runs succeeded`,
      pct: kpis.run_success_rate,
      color: "#A9C6AE",
    },
    {
      icon: BookOpen,
      label: "Citation Rate",
      value: `${kpis.citation_rate}%`,
      sub: "avg % of claims with citations",
      pct: kpis.citation_rate,
      color: "#93B6C4",
    },
    {
      icon: TrendingUp,
      label: "Source Coverage",
      value: kpis.source_coverage.toFixed(1),
      sub: "avg sources used per run",
      // Normalise against a target of 8 sources
      pct: Math.min((kpis.source_coverage / 8) * 100, 100),
      color: "#E8C4A2",
    },
    {
      icon: Clock,
      label: "Avg Run Duration",
      value: formatDuration(kpis.avg_duration_seconds),
      sub: "mean wall-clock time per run",
      // Normalise against a 5-minute target; shorter = better, so invert
      pct: kpis.avg_duration_seconds > 0
        ? Math.max(0, 100 - (kpis.avg_duration_seconds / 300) * 100)
        : 0,
      color: "#C98B7A",
    },
    {
      icon: AlertTriangle,
      label: "Publish Rate",
      value: `${kpis.publish_rate}%`,
      sub: `${kpis.published_runs} briefings published`,
      pct: kpis.publish_rate,
      color: "#A9C6AE",
    },
  ];

  return (
    <section aria-label="KPI Dashboard">
      <p className="eyebrow mb-3">Business KPIs</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {cards.map((c) => (
          <KpiCard key={c.label} {...c} />
        ))}
      </div>

      {/* Summary row */}
      <div className="mt-3 clay-inset rounded-[20px] px-5 py-3 flex flex-wrap gap-4 items-center">
        <span className="text-xs" style={{ color: "#2E2A22" }}>
          <span className="font-semibold" style={{ color: "#2E2A22" }}>{kpis.total_runs}</span> total runs
        </span>
        <span className="text-xs" style={{ color: "#2E2A22" }}>
          <span className="font-semibold" style={{ color: "#A9C6AE" }}>{kpis.successful_runs}</span> succeeded
        </span>
        <span className="text-xs" style={{ color: "#2E2A22" }}>
          <span className="font-semibold" style={{ color: "#C98B7A" }}>{kpis.failed_runs}</span> failed
        </span>
        <span className="text-xs" style={{ color: "#2E2A22" }}>
          <span className="font-semibold" style={{ color: "#93B6C4" }}>{kpis.published_runs}</span> published
        </span>
      </div>
    </section>
  );
}
