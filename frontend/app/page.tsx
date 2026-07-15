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

function FloatingOrbs() {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 500 320"
      fill="none"
      aria-hidden="true"
    >
      {/* Large back orb */}
      <ellipse cx="420" cy="60" rx="90" ry="90"
        fill="url(#orb1)" opacity="0.35" />
      {/* Mid orb */}
      <ellipse cx="60" cy="260" rx="70" ry="70"
        fill="url(#orb2)" opacity="0.30" />
      {/* Small accent */}
      <circle cx="380" cy="270" r="36"
        fill="url(#orb3)" opacity="0.28" />
      <circle cx="160" cy="40" r="24"
        fill="url(#orb4)" opacity="0.25" />

      {/* 3D sphere highlight rings */}
      <ellipse cx="420" cy="40" rx="38" ry="18"
        fill="rgba(255,255,255,0.25)" />
      <ellipse cx="60" cy="245" rx="28" ry="13"
        fill="rgba(255,255,255,0.20)" />

      <defs>
        <radialGradient id="orb1" cx="35%" cy="30%" r="60%">
          <stop offset="0%" stopColor="#A9C6AE" />
          <stop offset="100%" stopColor="#6fa87a" />
        </radialGradient>
        <radialGradient id="orb2" cx="35%" cy="30%" r="60%">
          <stop offset="0%" stopColor="#93B6C4" />
          <stop offset="100%" stopColor="#5a8fa0" />
        </radialGradient>
        <radialGradient id="orb3" cx="35%" cy="30%" r="60%">
          <stop offset="0%" stopColor="#E8C4A2" />
          <stop offset="100%" stopColor="#c9956a" />
        </radialGradient>
        <radialGradient id="orb4" cx="35%" cy="30%" r="60%">
          <stop offset="0%" stopColor="#C98B7A" />
          <stop offset="100%" stopColor="#a05e50" />
        </radialGradient>
      </defs>
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
        <p className="eyebrow mb-2">MarketPulse</p>
        <h1
          className="text-4xl font-bold leading-tight"
          style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
        >
          New Briefing
        </h1>
        <p className="mt-2 text-base font-medium" style={{ color: "#2E2A22" }}>
          Enter a topic and the AI crew will research, analyse, and draft a
          fully-sourced competitive-intelligence report.
        </p>
      </div>

      {/* Hero card with 3D orb decorations */}
      <div className="clay-hero p-8 relative overflow-hidden">
        <FloatingOrbs />

        <div className="relative z-10">
          <form onSubmit={handleSubmit} className="flex flex-col gap-6">
            {/* Topic input */}
            <label className="flex flex-col gap-2">
              <span className="eyebrow">Research Topic</span>
              <div className="clay-inset rounded-[20px] flex items-center gap-3 px-4 py-3.5">
                <Sparkles size={18} strokeWidth={2} color="#6B6358" className="shrink-0" />
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. AI developer tools market 2026"
                  disabled={loading}
                  className="flex-1 bg-transparent text-[15px] outline-none placeholder:text-[#4A4438] disabled:opacity-60"
                  style={{ color: "#2E2A22", fontFamily: "var(--font-inter), Inter, sans-serif" }}
                  aria-label="Research topic"
                />
              </div>
            </label>

            {/* Error */}
            {error && (
              <p className="text-sm font-medium px-1" style={{ color: "#a04030" }}>
                ⚠ {error}
              </p>
            )}

            {/* 3D Submit button */}
            <button
              type="submit"
              disabled={loading || !topic.trim()}
              className="self-start clay-btn-3d-green flex items-center gap-3 px-7 py-3.5 text-[15px] font-bold rounded-full disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ color: "#1a4024", fontFamily: "var(--font-poppins), Poppins, sans-serif" }}
            >
              {loading ? (
                <>
                  <span className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
                  Starting run…
                </>
              ) : (
                <>
                  Run Briefing
                  <ArrowRight size={17} strokeWidth={2.5} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>

      {/* Standing topics */}
      <div className="mt-8">
        <p className="eyebrow mb-3">Quick Topics</p>
        <div className="flex flex-wrap gap-2.5">
          {STANDING_TOPICS.map((t) => (
            <button
              key={t}
              onClick={() => setTopic(t)}
              disabled={loading}
              className="clay-btn-3d px-4 py-2.5 text-[13px] font-semibold rounded-full disabled:opacity-50"
              style={{
                color: "#2E2A22",
                fontFamily: "var(--font-poppins),sans-serif",
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Info strip */}
      <div className="clay-raised-sm mt-8 px-5 py-4 flex items-center gap-4">
        <div className="clay-knob w-10 h-10 flex items-center justify-center shrink-0">
          <Sparkles size={16} strokeWidth={2} color="#4A4438" />
        </div>
        <div>
          <p className="text-[14px] font-semibold" style={{ color: "#2E2A22" }}>5-agent AI pipeline</p>
          <p className="text-[13px] mt-0.5" style={{ color: "#2E2A22" }}>
            Coordinator → Researcher → Analyst → Fact-Checker → Writer · Typical run: 2–5 min
          </p>
        </div>
      </div>
    </div>
  );
}
