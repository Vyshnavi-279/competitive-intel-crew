"use client";

/**
 * PHASE 5 ADDITION — AuthPilotWrapper
 *
 * PILOT ONLY — NOT PRODUCTION AUTH.
 *
 * This client component is the sole isolation layer for the multi-tenant
 * auth pilot.  It:
 *   1. On mount, fetches GET /api/config to check multi_tenant_enabled.
 *   2. If false (the default) — renders children immediately, no change.
 *   3. If true — checks localStorage for a stored username.
 *      - If found, renders children and sets window.__mp_username so
 *        other components can read the current user for submitted_by.
 *      - If not found, renders the LoginModal first; on login, stores
 *        the username and renders children.
 *
 * Usage: wrap the layout's <main> content with this component.
 * When ENABLE_MULTI_TENANT_AUTH=false (default), this wrapper is a pure
 * pass-through — no visual change whatsoever.
 *
 * NOTE: This is explicitly a pilot.  The username is stored in localStorage
 * only — there is no session, no JWT, no server-side auth.  Do not use
 * this in production without replacing with a real auth solution.
 */

import { useEffect, useState } from "react";
import { LoginModal } from "@/components/LoginModal";

interface AuthPilotWrapperProps {
  children: React.ReactNode;
}

export function AuthPilotWrapper({ children }: AuthPilotWrapperProps) {
  // null = loading; false = pilot disabled; true = pilot enabled & needs auth
  const [pilotEnabled, setPilotEnabled] = useState<boolean | null>(null);
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    // Fetch config with a short timeout — if the API is unreachable, fall
    // through to non-pilot mode so a backend outage never locks the UI.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);

    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    fetch(`${API_BASE}/api/config`, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        clearTimeout(timeout);
        const enabled: boolean = Boolean(data?.multi_tenant_enabled);
        setPilotEnabled(enabled);

        if (enabled) {
          // Check localStorage for a previously stored name
          try {
            const stored = localStorage.getItem("mp_username");
            if (stored) {
              setUsername(stored);
              // Expose on window for other client components (e.g. triggerRun)
              (window as { __mp_username?: string }).__mp_username = stored;
            }
          } catch {
            // localStorage unavailable — proceed without stored name
          }
        }
      })
      .catch(() => {
        // Config fetch failed (network error, server down, etc.)
        // PILOT SAFE: fall through to non-pilot mode — do NOT block the UI.
        clearTimeout(timeout);
        setPilotEnabled(false);
      });

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  function handleLogin(name: string) {
    setUsername(name);
    // Expose globally so other components can attach submitted_by
    (window as { __mp_username?: string }).__mp_username = name;
  }

  // ---- Render logic -------------------------------------------------------

  // Still fetching config — render children immediately to avoid flash.
  // The modal will only appear if pilot is enabled AND no username is stored.
  if (pilotEnabled === null) {
    return <>{children}</>;
  }

  // Pilot disabled (default) — pure pass-through, no visual change
  if (!pilotEnabled) {
    return <>{children}</>;
  }

  // Pilot enabled + no username yet → show login modal
  if (pilotEnabled && !username) {
    return (
      <>
        {/* Render children beneath the modal so layout doesn't shift */}
        {children}
        <LoginModal onLogin={handleLogin} />
      </>
    );
  }

  // Pilot enabled + username present — render normally
  return <>{children}</>;
}
