"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FilePlus, LayoutDashboard, Settings, Zap, History, BarChart2 } from "lucide-react";

const NAV_ITEMS = [
  { href: "/",          icon: FilePlus,        label: "New Briefing",     color: "#A9C6AE" },
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard",        color: "#93B6C4" },
  { href: "/history",   icon: History,         label: "History",          color: "#E8C4A2" },
  // PHASE 4 ADDITION — Usage Analytics link (additive, existing items unchanged)
  { href: "/analytics", icon: BarChart2,       label: "Usage Analytics",  color: "#A9C6AE" },
  { href: "/settings",  icon: Settings,        label: "Settings",         color: "#C98B7A" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="flex flex-col gap-3 py-7 px-4 w-[200px] shrink-0 sticky top-0 h-screen"
      style={{
        background: "linear-gradient(180deg, #F7F2E9 0%, #EDE4D4 100%)",
        boxShadow: "4px 0 24px rgba(74,68,56,0.10)",
        borderRight: "1px solid rgba(74,68,56,0.07)",
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-2 mb-6">
        <div
          className="clay-knob flex items-center justify-center w-11 h-11 shrink-0"
          aria-label="MarketPulse"
        >
          <Zap size={20} strokeWidth={2.5} color="#4A4438" />
        </div>
        <div>
          <p
            className="font-bold text-base leading-tight"
            style={{ fontFamily: "var(--font-poppins),sans-serif", color: "#2E2A22" }}
          >
            MarketPulse
          </p>
          <p className="eyebrow mt-0.5">Intel Crew</p>
        </div>
      </div>

      {/* Nav label */}
      <p className="eyebrow px-3 mb-1">Navigation</p>

      {/* Nav items — 3D raised buttons when active */}
      <nav className="flex flex-col gap-2 flex-1" aria-label="Main navigation">
        {NAV_ITEMS.map(({ href, icon: Icon, label, color }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              aria-label={label}
              className={[
                "flex items-center gap-3 px-4 py-3 rounded-2xl transition-all duration-200",
                active
                  ? "sidebar-item-active"
                  : "hover:sidebar-item-hover",
              ].join(" ")}
              style={active ? { transform: "scale(1.02)" } : {}}
            >
              {/* Icon knob */}
              <span
                className="flex items-center justify-center w-8 h-8 rounded-xl shrink-0"
                style={active ? {
                  background: `linear-gradient(145deg, ${color}33, ${color}88)`,
                  boxShadow: `3px 3px 7px rgba(74,68,56,0.18), -2px -2px 5px rgba(255,255,255,0.75)`,
                } : {
                  background: "transparent",
                }}
              >
                <Icon
                  size={17}
                  strokeWidth={active ? 2.5 : 2}
                  color={active ? "#2E2A22" : "#6B6358"}
                />
              </span>

              <span
                className="text-[14px] font-semibold leading-none"
                style={{
                  fontFamily: "var(--font-poppins),sans-serif",
                  color: active ? "#2E2A22" : "#6B6358",
                }}
              >
                {label}
              </span>

              {/* Active indicator dot */}
              {active && (
                <span
                  className="ml-auto w-2 h-2 rounded-full shrink-0"
                  style={{ background: color }}
                  aria-hidden="true"
                />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Bottom section */}
      <div className="clay-inset rounded-2xl px-4 py-3 mt-2">
        <p className="eyebrow mb-1">System</p>
        <p className="text-[12px] font-medium" style={{ color: "#2E2A22" }}>MarketPulse</p>
        <p className="text-[11px]" style={{ color: "#6B6358" }}>v0.1 · Multi-agent AI</p>
      </div>
    </aside>
  );
}
