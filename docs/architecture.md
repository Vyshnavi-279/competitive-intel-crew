# Architecture — MarketPulse Competitive Intelligence Crew

## System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  INPUT                                                          │
│  User (dashboard) or Scheduler (Monday 08:00)                   │
│         │  topic string + triggered_by flag                     │
└─────────┬───────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  CREWAI SEQUENTIAL PIPELINE                                     │
│                                                                 │
│  1. Coordinator      Plans the three-section outline.           │
│         │            Does not call any tools; produces a        │
│         │            bullet-point brief for downstream agents.  │
│         ▼                                                       │
│  2. Researcher       Issues web searches via SafeSearchTool.    │
│         │            Capped at MAX_SOURCES per run (env var).   │
│         │            Tool catches all exceptions; skipped       │
│         │            queries are recorded, never crash the run. │
│         ▼                                                       │
│  3. Analyst          Reads raw research, extracts claims,       │
│         │            distinguishes verified from single-source. │
│         │            No external tools; pure LLM reasoning.     │
│         ▼                                                       │
│  4. Writer           Produces structured markdown with inline   │
│                      citation markers [Source](url) in every    │
│                      factual claim.                             │
└─────────┬───────────────────────────────────────────────────────┘
          │  raw markdown output
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOVERNANCE LAYER  (programmatic, not prompt-based)             │
│                                                                 │
│  enforce_citations            Drop any Claim with zero          │
│                               citations. Uncited claims never   │
│                               reach the user.                   │
│                                                                 │
│  flag_unverified_assertions   Detect high-risk keywords         │
│                               (bankrupt, lawsuit, fraud …)      │
│                               with a single non-trusted source. │
│                               Prefix with "Unverified:" and     │
│                               set verified=False rather than    │
│                               silently dropping.                │
│                                                                 │
│  RunGuard                     MAX_STEPS and MAX_EXECUTION_      │
│                               SECONDS caps prevent runaway      │
│                               agent loops.                      │
└─────────┬───────────────────────────────────────────────────────┘
          │  Briefing object, status = pending_review
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  HUMAN REVIEW GATE                                              │
│                                                                 │
│  Every briefing — whether triggered manually or by the          │
│  scheduler — lands in pending_review before any distribution.  │
│                                                                 │
│  Reviewer actions (via dashboard or API):                       │
│    POST /api/runs/{id}/publish  →  status: published            │
│    POST /api/runs/{id}/reject   →  status: rejected + reason    │
│                                                                 │
│  Why it exists: the briefing goes to VP-level decision-makers.  │
│  A single hallucinated pricing claim or misattributed lawsuit   │
│  could trigger a wrong strategic decision. The gate costs one   │
│  human 2–3 minutes per week; the downside risk of skipping it   │
│  is much higher.                                                │
└─────────┬───────────────────────────────────────────────────────┘
          │  status: published
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  STORAGE & SURFACING                                            │
│                                                                 │
│  SQLite  runs table        full briefing JSON + metadata        │
│          audit_log table   every state transition with          │
│                            timestamp + triggered_by             │
│                                                                 │
│  FastAPI REST API          GET /api/runs, GET /api/runs/{id}    │
│  Next.js 14 dashboard      history sidebar, BriefingCards,      │
│                            ReliabilityPanel, ReviewGate UI      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tools and Why They Were Chosen

**SafeSearchTool (wraps Serper API)**
Serper gives structured Google Search results via a simple REST API at low cost. The wrapper adds two things the raw tool lacks: a per-run cap (`MAX_SOURCES`, default 15) that stops runaway agent loops from exhausting quota, and a `try/except` shield that converts any network or auth failure into a skipped-source record rather than a crash. Both are essential for a production reporting pipeline.

**CrewAI sequential process**
A single monolithic agent produces shallow, poorly-structured output. Separating concerns across Coordinator → Researcher → Analyst → Writer means each agent has a tightly scoped role and a well-defined expected output format. The sequential process ensures every downstream agent has access to the full context of all prior tasks — critical for the Analyst to correctly attribute claims from the Researcher's raw findings.

**APScheduler BackgroundScheduler**
Runs inside the same FastAPI process (no separate worker or queue). Sufficient for a low-frequency weekly job; eliminates the operational overhead of Celery/Redis for a reporting tool that fires once per week. The `triggered_by` field distinguishes scheduler-fired runs from manual ones in the audit trail.

**SQLite + stdlib sqlite3**
The briefing volume is low (one to several runs per week). SQLite's zero-configuration model is the right fit — no database server to provision, backup is a single file copy, and the `INSERT OR REPLACE` pattern makes re-saving an updated briefing after a status change straightforward.

---

## Data Source

All competitive-intelligence content is sourced from **live web search** via the Serper API (Google Search). Each Researcher agent invocation issues targeted queries against the current web — pricing pages, press releases, news articles, SEC filings — returning titles, snippets, and URLs that the Analyst then reasons over. There is no static dataset; every briefing reflects the state of the web at the moment it was generated, which is both a strength (freshness) and a risk (the governance layer exists precisely because live web content is noisy and occasionally wrong).

---

## Evaluation Coverage

| Layer | What is tested |
|-------|----------------|
| Trace — full pipeline | `POST /api/run` returns 200 with 3 correctly-ordered sections and every claim cited |
| Failure handling | Mid-run source exceptions → run completes with `status=completed`, `sources_skipped` non-empty |
| Governance — citations | `enforce_citations` drops zero-citation claims and adds a flag entry |
| Trace — reliability | `SafeSearchTool` refuses calls beyond `MAX_SOURCES` without raising |
| Adversarial — governance | `flag_unverified_assertions` prefixes single-source high-risk claims with `"Unverified:"` |

Tests use FastAPI's `TestClient` for HTTP-level scenarios and direct function calls for unit-level governance tests. All external network calls are mocked so the suite is deterministic and runs offline.
