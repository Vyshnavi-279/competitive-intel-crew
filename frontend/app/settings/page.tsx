"use client";

import { useState } from "react";
import { Clock, Plus, X, Calendar } from "lucide-react";

const INITIAL_TOPICS = [
  "AI developer tools market 2026",
  "Cloud infrastructure pricing trends",
  "Open-source LLM landscape",
];

export default function SettingsPage() {
  const [topics, setTopics] = useState<string[]>(INITIAL_TOPICS);
  const [newTopic, setNewTopic] = useState("");

  function addTopic() {
    const t = newTopic.trim();
    if (!t || topics.includes(t)) return;
    setTopics([...topics, t]);
    setNewTopic("");
  }

  function removeTopic(t: string) {
    setTopics(topics.filter((x) => x !== t));
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") { e.preventDefault(); addTopic(); }
  }

  return (
    <div className="max-w-xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <p className="eyebrow mb-1">Configuration</p>
        <h1
          className="text-3xl font-semibold"
          style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
        >
          Settings
        </h1>
        <p className="mt-1 text-sm" style={{ color: "#2E2A22" }}>
          Configure standing topics and the weekly briefing schedule.
        </p>
      </div>

      {/* Schedule card */}
      <div className="clay-raised p-6 mb-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="clay-knob flex items-center justify-center w-10 h-10">
            <Clock size={16} strokeWidth={2} color="#4A4438" />
          </span>
          <div>
            <p className="eyebrow">Weekly Schedule</p>
            <p
              className="text-base font-semibold mt-0.5"
              style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
            >
              Every Monday at 08:00
            </p>
          </div>
        </div>

        <div className="clay-inset rounded-[16px] p-4">
          <div className="flex items-start gap-2.5">
            <Calendar size={14} strokeWidth={2} color="#4A4438" className="shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-medium" style={{ color: "#2E2A22" }}>
                Automated runs fire every Monday at 08:00 server-local time.
              </p>
              <p className="text-xs mt-1" style={{ color: "#2E2A22" }}>
                Triggered by <code className="text-[11px] bg-white/40 px-1 rounded">STANDING_TOPICS</code> env var.
                Change the schedule via <code className="text-[11px] bg-white/40 px-1 rounded">SCHEDULER_HOUR</code> /
                <code className="text-[11px] bg-white/40 px-1 rounded"> SCHEDULER_DAY_OF_WEEK</code>.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Standing topics card */}
      <div className="clay-raised p-6">
        <p className="eyebrow mb-1">Standing Topics</p>
        <p className="text-xs mb-5" style={{ color: "#2E2A22" }}>
          These topics are automatically briefed each week. They reflect the
          <code className="mx-1 text-[11px] bg-white/40 px-1 rounded">STANDING_TOPICS</code>
          environment variable.
        </p>

        {/* Topic chips */}
        {topics.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-5">
            {topics.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-2 px-3 py-1.5 text-[12px] font-medium rounded-full"
                style={{
                  background: "#f5e2ce",
                  color: "#7a5030",
                  boxShadow: "inset 3px 3px 6px rgba(74,68,56,0.10), inset -3px -3px 6px rgba(255,255,255,0.5)",
                }}
              >
                {t}
                <button
                  onClick={() => removeTopic(t)}
                  className="w-4 h-4 rounded-full flex items-center justify-center hover:brightness-90 transition-all"
                  style={{ background: "rgba(74,68,56,0.12)" }}
                  aria-label={`Remove ${t}`}
                >
                  <X size={9} strokeWidth={3} color="#7a5030" />
                </button>
              </span>
            ))}
          </div>
        )}

        {topics.length === 0 && (
          <p className="text-sm mb-5" style={{ color: "#2E2A22" }}>
            No standing topics. Add one below.
          </p>
        )}

        {/* Add new topic */}
        <div className="clay-inset rounded-[20px] flex items-center gap-3 px-4 py-3">
          <Plus size={15} strokeWidth={2.5} color="#4A4438" className="shrink-0" />
          <input
            type="text"
            value={newTopic}
            onChange={(e) => setNewTopic(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Add a standing topic…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-[#4A4438]"
            style={{ color: "#2E2A22" }}
            aria-label="New standing topic"
          />
          <button
            onClick={addTopic}
            disabled={!newTopic.trim()}
            className="clay-knob flex items-center justify-center w-7 h-7 disabled:opacity-40 hover:brightness-95 transition-all active:scale-90"
            aria-label="Add topic"
          >
            <Plus size={13} strokeWidth={2.5} color="#4A4438" />
          </button>
        </div>

        <p className="text-xs mt-3" style={{ color: "#2E2A22" }}>
          Note: changes here are local session state. Update <code className="text-[11px] bg-white/40 px-1 rounded">STANDING_TOPICS</code> in your <code className="text-[11px] bg-white/40 px-1 rounded">.env</code> to persist across restarts.
        </p>
      </div>
    </div>
  );
}
