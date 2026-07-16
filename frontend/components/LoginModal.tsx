"use client";

/**
 * PHASE 5 ADDITION — LoginModal
 *
 * PILOT ONLY — NOT PRODUCTION AUTH.
 * This is a minimal username-only login modal for the multi-tenant pilot.
 * No password, no session management, no security — just captures a name
 * and stores it in localStorage so every run knows who submitted it.
 *
 * This component only renders when GET /api/config returns:
 *   { "multi_tenant_enabled": true }
 *
 * When ENABLE_MULTI_TENANT_AUTH=false (the default), this component never
 * mounts and the app behaves exactly as it does without this file.
 */

import { useState } from "react";
import { UserCircle, ArrowRight } from "lucide-react";

interface LoginModalProps {
  onLogin: (username: string) => void;
}

export function LoginModal({ onLogin }: LoginModalProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Please enter your name to continue.");
      return;
    }
    // PILOT: store in localStorage so it persists across page refreshes
    // within the same browser session.
    try {
      localStorage.setItem("mp_username", trimmed);
    } catch {
      // localStorage unavailable — still allow login (just won't persist)
    }
    onLogin(trimmed);
  }

  return (
    /* Overlay */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(46, 42, 34, 0.5)", backdropFilter: "blur(4px)" }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="login-modal-title"
    >
      {/* Modal card */}
      <div
        className="w-full max-w-sm mx-4 rounded-[28px] p-8 flex flex-col gap-6"
        style={{
          background: "linear-gradient(145deg, #F7F2E9, #EDE4D4)",
          boxShadow: "8px 8px 20px rgba(74,68,56,0.22), -6px -6px 14px rgba(255,255,255,0.75)",
        }}
      >
        {/* Header */}
        <div className="flex flex-col items-center gap-3 text-center">
          {/* Icon knob */}
          <div
            className="flex items-center justify-center w-14 h-14 rounded-2xl"
            style={{
              background: "linear-gradient(145deg, #F7F2E9, #EDE4D4)",
              boxShadow: "5px 5px 12px rgba(74,68,56,0.2), -4px -4px 9px rgba(255,255,255,0.75)",
            }}
          >
            <UserCircle size={28} strokeWidth={1.8} color="#6B6358" />
          </div>
          <div>
            <p
              id="login-modal-title"
              className="text-xl font-semibold"
              style={{ fontFamily: "var(--font-poppins), Poppins, sans-serif", color: "#2E2A22" }}
            >
              Welcome to MarketPulse
            </p>
            <p className="text-[13px] mt-1" style={{ color: "#6B6358" }}>
              Enter your name to track your briefings.
            </p>
          </div>
        </div>

        {/* Pilot disclaimer */}
        <div
          className="rounded-xl px-4 py-2.5 text-[11px] text-center"
          style={{
            background: "#E8C4A233",
            color: "#7a5a2a",
            fontFamily: "var(--font-poppins), Poppins, sans-serif",
          }}
        >
          Pilot mode — no password required. This is not production authentication.
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <label className="flex flex-col gap-2">
            <span
              className="text-[11px] font-bold tracking-widest uppercase"
              style={{ color: "#9A9086", fontFamily: "var(--font-poppins), Poppins, sans-serif", letterSpacing: "0.1em" }}
            >
              Your Name
            </span>
            <div
              className="flex items-center gap-3 rounded-[16px] px-4 py-3"
              style={{
                background: "#F7F2E9",
                boxShadow: "inset 3px 3px 7px rgba(74,68,56,0.15), inset -2px -2px 5px rgba(255,255,255,0.7)",
              }}
            >
              <UserCircle size={16} strokeWidth={1.8} color="#6B6358" className="shrink-0" />
              <input
                type="text"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (error) setError(null);
                }}
                placeholder="e.g. Alice"
                autoFocus
                className="flex-1 bg-transparent text-[14px] outline-none placeholder:text-[#9A9086]"
                style={{ color: "#2E2A22", fontFamily: "var(--font-inter), Inter, sans-serif" }}
                aria-label="Your name"
                maxLength={80}
              />
            </div>
          </label>

          {error && (
            <p className="text-[12px]" style={{ color: "#C98B7A" }}>
              ⚠ {error}
            </p>
          )}

          <button
            type="submit"
            disabled={!name.trim()}
            className="flex items-center justify-center gap-2 px-6 py-3 text-[14px] font-bold rounded-full disabled:opacity-50 disabled:cursor-not-allowed hover:brightness-95 active:scale-95 transition-all"
            style={{
              background: "linear-gradient(145deg, #A9C6AE, #6fa87a)",
              boxShadow: "4px 4px 10px rgba(74,68,56,0.2), -3px -3px 8px rgba(255,255,255,0.7)",
              color: "#1a4024",
              fontFamily: "var(--font-poppins), Poppins, sans-serif",
            }}
          >
            Continue
            <ArrowRight size={16} strokeWidth={2.5} />
          </button>
        </form>
      </div>
    </div>
  );
}
