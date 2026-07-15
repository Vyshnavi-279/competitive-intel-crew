"use client";

import {
  Users,
  Search,
  BarChart2,
  ShieldCheck,
  PenLine,
  Check,
} from "lucide-react";
import type { RunStatus } from "@/lib/types";

export type AgentNodeStatus = "upcoming" | "active" | "done";

export interface AgentNode {
  id: string;
  label: string;
  caption?: string; // e.g. "14 sources found"
  status: AgentNodeStatus;
}

interface AgentChainProps {
  agents: AgentNode[];
}

const ICONS: Record<string, React.ElementType> = {
  coordinator: Users,
  researcher:  Search,
  analyst:     BarChart2,
  "fact-checker": ShieldCheck,
  writer:      PenLine,
};

function getIcon(id: string): React.ElementType {
  return ICONS[id.toLowerCase()] ?? Users;
}

function NodeKnob({ agent }: { agent: AgentNode }) {
  const Icon = getIcon(agent.id);

  let knobClass = "";
  let iconColor = "#8C8474";
  let iconOpacity = 0.45;

  if (agent.status === "upcoming") {
    knobClass = "clay-knob--upcoming";
  } else if (agent.status === "active") {
    knobClass = "clay-knob--active";
    iconColor = "#2c6478";
    iconOpacity = 1;
  } else {
    knobClass = "clay-knob--done";
    iconColor = "#3a6b42";
    iconOpacity = 1;
  }

  return (
    <div className="flex flex-col items-center gap-2 min-w-[72px]">
      {/* Knob */}
      <div className={`relative flex items-center justify-center w-14 h-14 ${knobClass}`}>
        <Icon
          size={22}
          strokeWidth={2}
          color={iconColor}
          style={{ opacity: iconOpacity }}
        />
        {/* Done badge */}
        {agent.status === "done" && (
          <span
            className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center clay-knob--done"
            aria-hidden="true"
          >
            <Check size={10} strokeWidth={3} color="#3a6b42" />
          </span>
        )}
      </div>

      {/* Label */}
      <span
        className="text-[11px] font-semibold text-center leading-tight"
        style={{
          color: agent.status === "upcoming" ? "#8C8474" : "#4A4438",
          fontFamily: "var(--font-poppins), Poppins, sans-serif",
        }}
      >
        {agent.label}
      </span>

      {/* Caption */}
      {agent.caption && (
        <span className="text-[10px] text-center leading-snug max-w-[72px]" style={{ color: "#8C8474" }}>
          {agent.caption}
        </span>
      )}
    </div>
  );
}

function Rail({ fromStatus, toStatus }: { fromStatus: AgentNodeStatus; toStatus: AgentNodeStatus }) {
  const done = fromStatus === "done" && (toStatus === "done" || toStatus === "active");
  return (
    <div className="flex-1 h-1.5 mx-1 mt-6 rounded-full clay-inset" style={{ minWidth: 24 }}>
      {done && (
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ background: "#A9C6AE", width: "100%" }}
        />
      )}
    </div>
  );
}

export function AgentChain({ agents }: AgentChainProps) {
  return (
    <div className="flex items-start gap-1 overflow-x-auto pb-2" role="list" aria-label="Agent pipeline">
      {agents.map((agent, i) => (
        <div key={agent.id} className="flex items-start" role="listitem">
          <NodeKnob agent={agent} />
          {i < agents.length - 1 && (
            <Rail fromStatus={agent.status} toStatus={agents[i + 1].status} />
          )}
        </div>
      ))}
    </div>
  );
}

/** Build agent list from a run status — derives which agents are active/done */
export function buildAgentNodes(runStatus: RunStatus, sourcesFound?: number): AgentNode[] {
  const agentDefs: Omit<AgentNode, "status">[] = [
    { id: "coordinator",   label: "Coordinator"   },
    { id: "researcher",    label: "Researcher"     },
    { id: "analyst",       label: "Analyst"        },
    { id: "fact-checker",  label: "Fact-Checker"   },
    { id: "writer",        label: "Writer"         },
  ];

  if (runStatus === "running") {
    // Heuristic: mark first two done, third active, rest upcoming
    return agentDefs.map((a, i) => ({
      ...a,
      status: i < 2 ? "done" : i === 2 ? "active" : "upcoming",
      caption: i === 1 && sourcesFound != null ? `${sourcesFound} sources` : undefined,
    }));
  }

  if (runStatus === "failed") {
    return agentDefs.map((a, i) => ({
      ...a,
      status: (i < 2 ? "done" : "upcoming") as AgentNodeStatus,
    }));
  }

  // completed / pending_review / published / rejected — all done
  return agentDefs.map((a, i) => ({
    ...a,
    status: "done",
    caption:
      i === 1 && sourcesFound != null ? `${sourcesFound} sources` : undefined,
  }));
}
