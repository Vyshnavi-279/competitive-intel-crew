# SPEC.md — Competitive Intelligence Briefing Crew

**Version:** 1.0
**Capstone Project 02 · Strategy / Sales Enablement**
**Business owner:** VP Strategy
**Status:** Draft for build

---

## 1. Purpose

Strategy and sales-enablement teams need a trustworthy, repeatable weekly read on competitor moves and market signals. Today this is assembled by hand over multiple days, which is slow, inconsistent between analysts, and often stale by the time it's read.

This system replaces that manual process with a multi-agent pipeline that researches, analyzes, and writes a cited weekly briefing on a chosen market — bounded, governed, and resilient to partial failure — so the VP Strategy can act on it directly.

---

## 2. Scope

### 2.1 In scope (MVP)
- A 4-agent sequential crew: Coordinator, Researcher, Analyst, Writer.
- Web search over a live source set (no static/offline corpus).
- Exactly 3 output sections: Executive Summary (with a recommendation), Competitor Pricing & Product Moves, Market Signals.
- Per-claim citation enforcement.
- Partial source-failure handling (skip, log, continue).
- Hard bounds on source count and total agent steps.
- Run metadata (duration, tokens, sources used/skipped) attached to every briefing.
- A dashboard to trigger runs and view briefings.
- An automated evaluation suite covering 5 scenarios.

### 2.2 In scope (stretch — included in this build)
- A Fact-Checker agent that cross-verifies claims against a second independent source.
- A human review/approval gate before a briefing is marked "published."
- Scheduled weekly automated runs.

### 2.3 Out of scope
- Multi-tenant auth/user accounts (single-user/team tool for the capstone).
- Editing a briefing's text after generation (only approve/reject).
- Any action that spends money, contacts a customer, or modifies external systems — this system only reads and reports.
- Support for languages other than English.
- A production-grade vector database (a lightweight optional cache is a future enhancement, not required here).

---

## 3. Users and success metrics

| | |
|---|---|
| **Primary user** | Strategy / sales-enablement analysts (trigger and review runs) |
| **Approver / reviewer** | VP Strategy (final "publish" decision) |
| **Consumers of output** | Strategy and sales teams reading the published briefing |

**KPIs:**
- Analyst hours saved per briefing cycle (manual baseline vs. system-assisted).
- Briefing turnaround time (topic submitted → briefing ready for review).
- % of claims cited (target: 100% — governance makes anything less impossible by construction).

---

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | The system accepts a market/topic string as input and returns a structured briefing. |
| FR-2 | A Coordinator plans and sequences the run; a Researcher gathers sources; an Analyst extracts and compares signal; a Writer produces the final briefing. |
| FR-3 | The briefing must contain exactly three sections: Executive Summary, Competitor Pricing & Product Moves, Market Signals. |
| FR-4 | Every claim in the final briefing must carry at least one citation (source name + URL where available). Claims without a citation must never reach the final output. |
| FR-5 | Claims that reference a serious, reputationally damaging assertion (e.g. bankruptcy, fraud, lawsuit) sourced from only one non-authoritative outlet must be hedged ("Unverified: ...") rather than stated as fact. |
| FR-6 | If a source is unreachable or times out, the run must skip it, record it as skipped, and still complete — never crash or hang. |
| FR-7 | The run must not exceed a configurable maximum number of source lookups (`MAX_SOURCES`) or agent steps (`MAX_STEPS`); once reached, the system stops gathering and proceeds to write with what it has. |
| FR-8 | Every completed run stores: run ID, topic, start time, duration, sources attempted/used/skipped, total steps, token estimate, and status. |
| FR-9 | A dashboard lets a user submit a topic, watch per-agent run status live (or near-live), and view the resulting briefing with visible citations. |
| FR-10 | A Fact-Checker agent attempts to independently corroborate each Analyst claim via a second source before the Writer finalizes the briefing; claims that cannot be corroborated are marked unverified rather than dropped, unless they also fail FR-4. |
| FR-11 | A completed, governance-passed briefing enters a "pending review" state; a human (VP Strategy) must explicitly approve ("publish") or reject it. Rejection requires an optional short reason and is logged. |
| FR-12 | The system can trigger runs automatically on a schedule (default weekly) against a configured list of standing topics, in addition to manual on-demand runs. Scheduled runs are distinguishable from manual runs in the stored data and the UI. |
| FR-13 | An evaluation suite runs the 5 required test scenarios (below) and produces a pass/fail report. |

---

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 (Bounded cost) | A single run must not exceed the configured source and step caps regardless of topic breadth. |
| NFR-2 (Resilience) | No single source failure may crash a run or leave it hanging past `MAX_EXECUTION_SECONDS`. |
| NFR-3 (Auditability) | Every run's key events (start, each agent's completion, skipped sources, governance actions, publish/reject decisions) are written to an append-only audit log. |
| NFR-4 (Model flexibility) | The LLM provider/model is configured via environment variables and routed through OpenRouter/LiteLLM so it can be swapped without code changes. |
| NFR-5 (Usability) | The dashboard must make trustworthiness visible at a glance: citation chips on every claim, a reliability panel showing skipped sources and dropped/hedged claims, and clear status badges (pending review / published / rejected). |
| NFR-6 (Reproducibility) | Given the same topic and the same web state, repeated runs should produce structurally consistent output (3 sections present, schema-valid) even if exact wording varies — this is checked by the eval suite, not by requiring byte-identical output. |

---

## 6. System architecture

```
User (topic input, dashboard)
        │
        ▼
   Coordinator  ── plans the run, sequences the pipeline
        │
        ▼
   Researcher   ── SafeSearchTool (web search, capped, fault-tolerant)
        │
        ▼
    Analyst     ── extracts claims + citations, separates signal from noise
        │
        ▼
  Fact-Checker  ── independently corroborates each claim via a 2nd source
        │
        ▼
    Writer      ── produces the 3-section structured briefing
        │
        ▼
 ── Governance layer (wraps the whole pipeline) ──
    • citation_guard: drops uncited claims
    • unverified-claim hedging: rewrites/flags single-source serious claims
    • run_guard: enforces MAX_SOURCES / MAX_STEPS / MAX_EXECUTION_SECONDS
        │
        ▼
  Human review gate (VP Strategy: approve → published / reject → rejected)
        │
        ▼
   Dashboard (Next.js) ── displays briefing, citations, reliability, history
        │
        ▼
   Storage (SQLite: runs, audit_log) ── read by API for history and eval

Scheduler (APScheduler) triggers the same pipeline weekly for standing topics,
independent of manual dashboard-triggered runs.
```

**Orchestration pattern:** CrewAI, `Process.sequential`. The pipeline order (Coordinator → Researcher → Analyst → Fact-Checker → Writer) is fixed by design — this is a reporting pipeline, not a free-form delegating agent, so predictability and evaluability were prioritized over flexibility.

---

## 7. Agent specifications

| Agent | Role / Goal | Tools | Inputs | Outputs |
|---|---|---|---|---|
| **Coordinator** | Plans the run; ensures all sections get produced in the right order | none | topic | a run plan (implicit — orchestrates task order) |
| **Researcher** | Gather ≥15 reachable sources covering pricing moves, product launches, market signals | `SafeSearchTool` (capped, fault-tolerant web search) | topic | raw findings + list of sources with URLs |
| **Analyst** | Compare findings, extract claims, attach citations, separate verified fact from single-source rumor | none (reasons over Researcher's output) | raw findings | list of `Claim` objects grouped by section |
| **Fact-Checker** | Independently corroborate each claim via a second, different source | `SafeSearchTool` (shared budget with Researcher) | Analyst's claims | claims marked `verified: true/false` |
| **Writer** | Produce the final 3-section, citation-tagged briefing with an executive recommendation | none | verified/flagged claims | structured `Briefing` (Pydantic) |

**Shared constraints across agents:** `max_iter` and `max_execution_time` set from `run_guard.py` constants; all web search calls (Researcher and Fact-Checker) draw from one shared `SafeSearchTool` instance so the total source budget (`MAX_SOURCES`) is never exceeded in aggregate.

---

## 8. Data model (Pydantic)

```
Citation      { source_name: str, url: Optional[str] }
Claim         { text: str, citations: List[Citation], verified: bool }
Section       { title: str  # one of the 3 fixed titles
                claims: List[Claim] }
RunMetadata   { run_id, topic, started_at, duration_seconds,
                sources_attempted, sources_used, sources_skipped: List[str],
                total_steps, token_estimate, triggered_by: "manual"|"scheduled",
                status: "running"|"completed"|"failed"|"pending_review"|"published"|"rejected" }
Briefing      { metadata: RunMetadata, sections: List[Section],
                unverified_flags: List[str] }
```

---

## 9. Governance rules (enforced in code, not only in prompts)

1. **No uncited claim ever reaches the final briefing.** `citation_guard.enforce_citations` removes any claim with zero citations and records why.
2. **No unverified serious claim is stated as fact.** `citation_guard.flag_unverified_assertions` detects reputationally sensitive language backed by only a single non-authoritative source and rewrites it as hedged ("Unverified: ...") rather than deleting it outright (the information may still be useful to a strategist, just clearly labeled).
3. **The run cannot exceed its budget.** `run_guard` constants cap total sources and total steps; `SafeSearchTool` self-enforces the source cap regardless of how many agents call it.
4. **A human must approve publication.** No briefing reaches "published" status without an explicit approve action from a reviewer; rejections are logged with a reason.
5. **Every governance action is logged.** Drops, hedges, skips, and publish/reject decisions are all written to `audit_log`.

---

## 10. Evaluation suite (5 required scenarios)

| # | Scenario | Layer | Given | Expected behavior | Pass criteria |
|---|---|---|---|---|---|
| 1 | Full weekly briefing | Trace (happy path) | Market topic with 15+ reachable sources | Runs Coordinator → Researcher → Analyst → Fact-Checker → Writer; produces all 3 sections, each cited | Correct agent sequence; every section present and cited |
| 2 | Source failure | Failure-handling | One source times out mid-run | Skips it, notes the gap, still completes | Run completes; failure noted; no crash/hang |
| 3 | Uncited claim | Governance / output | Analyst produces a claim with no supporting source | Claim is dropped, never published as fact | No uncited claim in the final briefing |
| 4 | Runaway guard | Trace / reliability | A very broad topic that could spawn endless searches | Stays within the source/step cap and terminates cleanly | Run bounded; terminates; budget respected |
| 5 | Planted unverified claim | Adversarial / governance | A source asserts something serious with no corroborating evidence | Not repeated as fact; hedged or omitted | Unverified/defamatory claim not stated as fact |

Additional coverage from stretch features:
- **Human gate check** — a completed run cannot appear as "published" without a recorded approval event in `audit_log`.
- **Scheduled run distinction** — a scheduled run's `triggered_by` field is correctly set to "scheduled" and appears distinctly in the UI/history.

---

## 11. API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/run` | Trigger a new manual run for a given topic |
| GET | `/api/runs` | List recent run summaries |
| GET | `/api/runs/{run_id}` | Full briefing + metadata for one run |
| POST | `/api/runs/{run_id}/publish` | Human approval → status becomes "published" |
| POST | `/api/runs/{run_id}/reject` | Human rejection (optional reason) → status becomes "rejected" |
| GET | `/api/health` | Liveness check |

---

## 12. Configuration (environment variables)

| Variable | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | LLM access via OpenRouter | — required |
| `SERPER_API_KEY` | Web search tool access | — required |
| `MODEL_NAME` | Model string routed through LiteLLM/OpenRouter | `openrouter/anthropic/claude-3.5-sonnet` |
| `MAX_SOURCES` | Hard cap on total source lookups per run | `15` |
| `MAX_STEPS` | Hard cap on total agent steps per run | `25` |
| `MAX_EXECUTION_SECONDS` | Wall-clock cap per run | `600` |
| `STANDING_TOPICS` | Comma-separated topics for the scheduler | one example topic |

---

## 13. Tech stack summary

| Layer | Choice |
|---|---|
| Agent orchestration | CrewAI (`Process.sequential`) |
| LLM routing | OpenRouter via LiteLLM |
| Web search tool | Serper.dev (`SerperDevTool`) |
| Backend API | FastAPI |
| Storage | SQLite (runs, audit_log) |
| Scheduling | APScheduler |
| Frontend | Next.js + TypeScript + Tailwind |
| Testing | pytest |

---

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| LLM invents a citation-looking string that doesn't map to a real source | Citation extraction validates against the Researcher's actual returned source list, not free-standing text from the Writer |
| Search API rate limits/costs spike on broad topics | `MAX_SOURCES` cap enforced at the tool level, shared across all agents |
| A single slow/hanging external call stalls the whole run | Per-call timeout + `MAX_EXECUTION_SECONDS` crew-level cap |
| Reviewer bottleneck delays every briefing | Reject path is fast (one click + optional reason); scheduled runs still generate in the background regardless of review backlog |
| Model swap changes output format enough to break parsing | Writer's output is constrained to the Pydantic schema; a parsing failure is treated as a failed run (status="failed"), not silently malformed output |

---

## 15. Deliverables checklist 

- [ ] Working demo: live run of the full pipeline end to end
- [ ] Evaluation report (`eval/eval_report.md`) covering all 5 scenarios
- [ ] One-page architecture doc (`docs/architecture.md`)
- [ ] Reflection doc (`docs/reflection.md`)
- [ ] This spec (`SPEC.md`) and `README.md`