"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FilePlus, History, Settings, Zap } from "lucide-react";

const NAV_ITEMS = [
  { href: "/",         icon: FilePlus,  label: "New Briefing" },
  { href: "/history",  icon: History,   label: "Run History"  },
  { href: "/settings", icon: Settings,  label: "Settings"     },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="flex flex-col items-center gap-6 py-8 px-3 w-[72px] shrink-0 sticky top-0 h-screen"
      style={{ background: "#F7F2E9" }}
    >
      {/* Logo knob */}
      <div
        className="clay-knob flex items-center justify-center w-11 h-11 mb-4 shrink-0"
        aria-label="MarketPulse"
      >
        <Zap size={18} strokeWidth={2.5} color="#4A4438" />
      </div>

      {/* Nav items */}
      <nav className="flex flex-col gap-4 flex-1" aria-label="Main navigation">
        {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              title={label}
              aria-label={label}
              className={[
                "flex items-center justify-center w-11 h-11 transition-all duration-200",
                active ? "clay-knob" : "clay-knob--upcoming hover:clay-knob",
              ].join(" ")}
            >
              <Icon
                size={18}
                strokeWidth={2}
                color={active ? "#4A4438" : "#8C8474"}
              />
              {active && (
                <span
                  className="absolute -right-1 w-2 h-2 rounded-full"
                  style={{ background: "#A9C6AE" }}
                  aria-hidden="true"
                />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Version eyebrow at bottom */}
      <span className="eyebrow select-none" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
        v0.1
      </span>
    </aside>
  );
}
