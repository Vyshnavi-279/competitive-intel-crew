"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, ArrowRight } from "lucide-react";
import { triggerRun } from "@/lib/api";

const STANDING_TOPICS = [
  "AI developer tools market 2026",
  "Cloud infrastructure pricing trends",
  "Open-source LLM landscape",
  "SaaS note-taking apps pricing",
  "Enterprise AI adoption signals",
];

// Simple leaf/dot decorative SVG for empty state
function EmptyStateDecoration() {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none opacity-30"
      viewBox="0 0 400 300"
      fill="none"
      aria-hidden="true"
    >
      {/* Soft leaf shapes */}
      <ellipse cx="60" cy="80" rx="28" ry="44" fill="#A9C6AE" transform="rotate(-30 60 80)" />
      <ellipse cx="340" cy="220" rx="22" ry="36" fill="#93B6C4" transform="rotate(20 340 220)" />
      <circle cx="320" cy="60" r="18" fill="#E8C4A2" />
      <circle cx="80" cy="240" r="12" fill="#C98B7A" opacity="0.5" />
      <ellipse cx="200" cy="270" rx="16" ry="26" fill="#A9C6AE" transform="rotate(10 200 270)" />
    </svg>
  );
}

export default function NewBriefingPage() {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = topic.trim();
    if (!t) return;
    setLoading(true);
    setError(null);
    try {
      const briefing = await triggerRun(t);
      router.push(`/runs/${briefing.metadata.run_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Page heading */}
      <div className="mb-8">
        <p className="eyebrow mb-1">MarketPulse</p>
        <h1
          className="text-3xl font-semibold leading-tight"
          style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#4A4438" }}
        >
          New Briefing
        </h1>
        <p className="mt-1 text-sm" style={{ color: "#8C8474" }}>
          Enter a topic and the crew will research, analyse, and draft a sourced competitive-intelligence report.
        </p>
      </div>

      {/* Hero card with decoration */}
      <div className="clay-hero p-8 relative overflow-hidden">
        <EmptyStateDecoration />

        <div className="relative z-10">
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            {/* Topic input */}
            <label className="flex flex-col gap-2">
              <span className="eyebrow">Research Topic</span>
              <div className="clay-inset rounded-[20px] flex items-center gap-3 px-4 py-3">
                <Sparkles size={16} strokeWidth={2} color="#8C8474" className="shrink-0" />
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. AI note-taking app pricing trends 2026"
                  disabled={loading}
                  className="flex-1 bg-transparent text-sm outline-none placeholder:text-[#8C8474] disabled:opacity-60"
                  style={{ color: "#4A4438", fontFamily: "var(--font-inter), Inter, sans-serif" }}
                  aria-label="Research topic"
                />
              </div>
            </label>

            {/* Error message */}
            {error && (
              <p className="text-sm px-1" style={{ color: "#C98B7A" }}>
                ⚠ {error}
              </p>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={loading || !topic.trim()}
              className="self-start clay-knob--done flex items-center gap-2.5 px-6 py-3 text-sm font-semibold rounded-full transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:brightness-95 active:scale-95"
              style={{ color: "#2e5e36", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
                  Starting run…
                </>
              ) : (
                <>
                  Run Briefing
                  <ArrowRight size={16} strokeWidth={2.5} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Standing topics */}
      <div className="mt-8">
        <p className="eyebrow mb-3">Standing Topics</p>
        <div className="flex flex-wrap gap-2">
          {STANDING_TOPICS.map((t) => (
            <button
              key={t}
              onClick={() => setTopic(t)}
              disabled={loading}
              className="clay-inset-pill px-3.5 py-2 text-[12px] font-medium transition-all duration-150 hover:brightness-95 active:scale-95 disabled:opacity-50"
              style={{
                color: "#8C8474",
                background: "#f5e2ce",
                boxShadow: "inset 3px 3px 6px rgba(74,68,56,0.10), inset -3px -3px 6px rgba(255,255,255,0.5)",
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Tip */}
      <p className="mt-6 text-xs" style={{ color: "#8C8474" }}>
        Runs take 2–5 minutes. You'll be taken to the live monitor automatically.
      </p>
    </div>
  );
}
