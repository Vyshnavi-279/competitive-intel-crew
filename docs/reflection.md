# Reflection — MarketPulse Development

---

## Analyst hours saved per briefing cycle

**Manual baseline (pre-system):**
A strategy analyst assembling a weekly competitive-intelligence briefing
manually would typically spend:

| Activity | Estimated time |
|---|---|
| Identifying and visiting 10–15 relevant sources | ~90 min |
| Reading, filtering, and note-taking | ~60 min |
| Drafting the three-section briefing structure | ~45 min |
| Adding inline citations and fact-checking claims | ~30 min |
| Formatting and distributing to stakeholders | ~15 min |
| **Total per cycle** | **~4 hours** |

This estimate aligns with informal benchmarks from research and intelligence
functions in mid-size strategy teams, where "competitive watch" tasks often
consume half a working day per analyst per week.

**System-assisted turnaround:**
A MarketPulse run (end-to-end: topic submitted → briefing ready for human
review) completes in roughly **2–5 minutes** of wall-clock time, depending on
API response latency and topic breadth.  The `duration_seconds` field in
`RunMetadata` records the exact elapsed time for each run; the dashboard
"Avg Run Duration" KPI card surfaces the mean across all completed runs.

**Net saving:**
Approximately **~3h 55m per briefing cycle per analyst** is reclaimed —
a reduction of roughly 95% in time-on-task.  The human reviewer still spends
5–10 minutes reading and approving (or rejecting) the briefing before it
reaches the broader org, which is intentional: the human review gate
(SPEC §4, FR-11) ensures a person validates the output rather than
auto-publishing LLM-generated analysis.

---

## What broke during development

- **LLM output format drift:** The Writer agent occasionally omitted one of
  the three required `##` headings or used a slightly different title variant
  (e.g. "Competitor Moves" instead of "Competitor Pricing & Product Moves").
  The heading normalizer in `crew.py` (`_normalize_section_title`) handles
  the common variants, but a future improvement would be to use structured
  output (JSON mode) to guarantee schema compliance rather than regex parsing.

- **Groq free-tier rate limits:** The 30 RPM and 6,000 TPM caps on Groq's
  free tier caused 429 errors on the first few real runs.  Fixing this required
  adding `litellm.num_retries=3`, per-agent `max_rpm=20`, and an outer
  exponential-backoff retry loop in `run_briefing()`.  Switching to a paid
  tier or a less constrained model would remove this entirely.

- **Citation extraction vs. prompt-only enforcement:** Initial runs showed
  that prompting the Writer to "always cite" was not sufficient — some bullets
  slipped through without citation markers.  The `citation_guard.enforce_citations`
  function (which drops uncited claims at the Python level, not in the prompt)
  was essential to actually achieve FR-4.

---

## What we'd harden before real production

- **Authentication on the API endpoints** — currently the FastAPI app accepts
  any request on port 8000.  A real deployment needs at minimum an API key
  header check or OAuth2 token validation to prevent unauthenticated briefing
  triggers and publishes.

- **Retry logic and back-off for Serper/OpenRouter rate-limit responses** —
  `SafeSearchTool` currently skips and logs failed searches but does not
  retry them.  A short exponential back-off (max 2 retries per source) would
  recover transient 429/503 errors without adding significant latency.

- **Replace SQLite with a proper database for concurrent writes** — SQLite
  serialises writes, which is fine for a single-user capstone tool but becomes
  a bottleneck under concurrent scheduled + manual runs.  PostgreSQL (or even
  DuckDB for analytical queries) would be the first upgrade for a team deployment.

- **Secrets management** — API keys currently live in `.env` on disk.  A
  production deployment should use a secrets manager (AWS Secrets Manager,
  HashiCorp Vault, or at minimum environment injection from a CI/CD system).

---

## What surprised us

- **CrewAI's context passing is implicit and lossy.** In `Process.sequential`,
  each task receives all prior tasks' outputs as context, but LLMs don't
  reliably forward all of it.  The Fact-Checker sometimes re-invented claims
  rather than verifying the Analyst's output verbatim.  Explicit context
  instructions in the task description ("Review the Analyst's EXACT claims")
  reduced but did not eliminate this drift.

- **Governance enforcement was more important than prompt quality.** The most
  reliable way to achieve 100% citation coverage was not a better prompt but
  `citation_guard.enforce_citations` running *after* the crew.  The final
  `cited_claims_pct` field in RunMetadata makes this verifiable at a glance —
  judges and reviewers don't have to trust the prompt; they can read the
  number.

- **The human review gate significantly improved output confidence.** Adding
  an approve/reject step (FR-11) was originally a stretch feature but turned
  out to be the most practically useful part of the system.  Every run that
  reached pending_review was meaningfully improved by having a human skim
  the reliability panel (dropped/hedged claims, skipped sources) before
  publishing.

---

## What we'd add with more time

- **Streaming agent progress over WebSocket** — the RunMonitor currently polls
  every 3 seconds.  Real-time streaming of per-agent status updates would make
  the "Live Monitor" page feel significantly more responsive, especially on
  longer runs.

- **Week-over-week diff view** — for standing topics (auto-scheduled runs),
  a diff panel highlighting what changed since the previous briefing would be
  more actionable than re-reading the full report from scratch.

- **Email/Slack delivery of published briefings** — reviewers currently have to
  visit the dashboard to see new briefings.  A webhook or email notification on
  publish would remove that friction and make MarketPulse genuinely autonomous
  for the "consumer of output" audience (SPEC §3).
