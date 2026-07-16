"""
CrewAI crew for the Competitive Intelligence Briefing.

WHY THIS ARCHITECTURE EXISTS:
A single monolithic agent tends to produce shallow, poorly‑structured output.
By splitting the work across five specialised agents (coordinator → researcher
→ analyst → fact-checker → writer) we get:
  - **Coordinator** — plans the sections and hands off to each downstream agent.
  - **Researcher** — gathers raw web data (capped by SafeSearchTool's runaway guard).
  - **Analyst** — reasons over the research to extract signal from noise.
  - **Fact-Checker** — cross-checks the Analyst's claims against raw research
    before the briefing reaches the governance layer (FR-10).
  - **Writer** — produces the final structured briefing with citation markers.

After the crew runs, two governance layers (*enforce_citations* and
*flag_unverified_assertions*) programmatically enforce citation quality —
prompts alone are not enough.

The entire run is wrapped in try/except so that *any* failure (API outage,
bad LLM response, etc.) returns a partial Briefing with status="failed"
instead of crashing the API layer.
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import List
from uuid import uuid4

import litellm  # FIX 1: import for retry / timeout configuration

from crewai import Agent, Crew, LLM, Process, Task
from dotenv import load_dotenv

from backend.governance.citation_guard import (
    enforce_citations,
    flag_unverified_assertions,
)
from backend.governance.run_guard import MAX_EXECUTION_SECONDS, MAX_STEPS
from backend.models.schemas import Briefing, Claim, Citation, RunMetadata, Section
from backend.tools.citation_tool import extract_citations, strip_citation_markers
from backend.tools.safe_search_tool import SafeSearchTool

from backend.config import settings

# ---------------------------------------------------------------------------
# PHASE 1 ADDITION — In-memory stage registry + DB-backed stage log
# ---------------------------------------------------------------------------
# _stage_registry holds the latest stage state per run_id so the API endpoint
# can return live data without hitting SQLite on every poll.  It's a plain
# dict (no locks needed — FastAPI runs crew tasks in a thread/async, and
# individual dict updates in CPython are atomic for our purposes).
# Format: { run_id: [ { stage_name, status, description, started_at, completed_at } ] }

_stage_registry: dict = {}

# Ordered stage definitions — name + one-line description of what's happening.
_STAGE_DEFS = [
    ("Coordinator",  "Planning the briefing outline and section structure"),
    ("Researcher",   "Searching the web for sources and raw data"),
    ("Analyst",      "Extracting and classifying claims from research"),
    ("Fact-Checker", "Cross-checking every claim against the raw research"),
    ("Writer",       "Composing the final structured briefing with citations"),
]


def _stage_start(run_id: str, stage_name: str, description: str) -> None:
    """Record a stage as 'running' in memory and in SQLite.

    Wrapped in a broad try/except — stage tracking must NEVER crash a run.
    """
    try:
        from backend.storage.db import save_stage_start as _db_start
        _db_start(run_id, stage_name, description)
    except Exception:
        pass  # DB failure is silent — in-memory registry still works

    try:
        from datetime import timezone
        registry = _stage_registry.setdefault(run_id, [])
        # Update existing entry or append a new one
        for entry in registry:
            if entry["stage_name"] == stage_name:
                entry["status"] = "running"
                entry["started_at"] = datetime.now(timezone.utc).isoformat()
                entry["completed_at"] = None
                return
        registry.append({
            "stage_name":   stage_name,
            "status":       "running",
            "description":  description,
            "started_at":   datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        })
    except Exception:
        pass


def _stage_end(run_id: str, stage_name: str, status: str = "done") -> None:
    """Mark a stage as done or failed in memory and in SQLite."""
    try:
        from backend.storage.db import save_stage_end as _db_end
        _db_end(run_id, stage_name, status)
    except Exception:
        pass

    try:
        from datetime import timezone
        registry = _stage_registry.get(run_id, [])
        for entry in registry:
            if entry["stage_name"] == stage_name:
                entry["status"] = status
                entry["completed_at"] = datetime.now(timezone.utc).isoformat()
                return
    except Exception:
        pass

# Configure litellm for Groq free-tier.
# num_retries=3: on a 429 litellm will retry up to 3 times, honouring the
# Retry-After header that Groq sends back (the actual seconds to wait).
# This means rate-limit errors are handled transparently at the LLM call
# level, before CrewAI's flow runtime ever sees them — eliminating the
# "failed to generate a valid tool call" error that occurred when the
# 429 interrupted a mid-execution tool-call round-trip.
litellm.num_retries = 3
litellm.request_timeout = 60  # raise from 30 — Groq can be slow under load

# load_dotenv is called by config.py at import time; calling it again here is
# harmless (override=True ensures the .env file wins over any stale env vars).
load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM configuration — Groq via CrewAI's LLM class
# ---------------------------------------------------------------------------
# Use settings (which guarantees .env was loaded) instead of bare os.getenv
# so values like MODEL_NAME, GROQ_API_KEY, and MAX_TOKENS are always correct.
#
# Groq does not support the 'cache_breakpoint' extra field that CrewAI injects
# into messages for Anthropic prompt-caching.  When any non-Anthropic provider
# is configured we monkey-patch mark_cache_breakpoint to be a no-op so the
# field is never sent, avoiding GroqException "property 'cache_breakpoint' is
# unsupported".
os.environ["LITELLM_DISABLE_PROMPT_CACHING"] = "true"

if "anthropic" not in settings.model_name.lower():
    import crewai.llms.cache as _crewai_cache
    import crewai.agents.crew_agent_executor as _crew_exec

    def _noop_mark_cache_breakpoint(message: dict) -> dict:
        """Return the message unchanged — provider doesn't support cache hints."""
        return message

    # Patch the canonical cache module so any local `from crewai.llms.cache
    # import mark_cache_breakpoint` done at call-time picks up the no-op.
    _crewai_cache.mark_cache_breakpoint = _noop_mark_cache_breakpoint
    # Also patch the already-imported module-level reference in the standard
    # agent executor (it imports the symbol at module load time).
    _crew_exec.mark_cache_breakpoint = _noop_mark_cache_breakpoint  # type: ignore[attr-defined]

    # Patch the experimental executor module-level reference too.
    try:
        import crewai.experimental.agent_executor as _exp_exec
        _exp_exec.mark_cache_breakpoint = _noop_mark_cache_breakpoint  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pass

llm = LLM(
    model=settings.model_name,          # writer + coordinator (need quality)
    api_key=settings.llm_api_key,
    max_tokens=settings.max_tokens,
)

# WHY ALL AGENTS USE THE SAME MODEL:
# llama-3.1-8b-instant has a 6,000 TPM (tokens-per-minute) limit on Groq's
# free tier.  A single researcher tool-call round-trip (system prompt + tool
# schema + conversation history + response) easily consumes 1,500–5,000
# tokens, exhausting the bucket within 1-2 calls and producing a 429
# RateLimitError that CrewAI surfaces as "failed to generate a valid tool
# call".  llama-3.3-70b-versatile has a 12,000 TPM free-tier limit — double
# the headroom — and handles function/tool calling more reliably.
# We use a single LLM object for all agents so there is only one token bucket
# to manage and the inter-agent sleep delays (below) keep us inside the limit.
_researcher_llm = LLM(
    model=settings.model_name,   # groq/llama-3.3-70b-versatile — 12k TPM, reliable tool calls
    api_key=settings.llm_api_key,
    max_tokens=1024,
)

_analyst_llm = LLM(
    model=settings.model_name,   # groq/llama-3.3-70b-versatile — consistent with researcher
    api_key=settings.llm_api_key,
    max_tokens=1500,
)

# ---------------------------------------------------------------------------
# Shared tool instances (stateful — counts are read after the run)
# ---------------------------------------------------------------------------

_search_tool = SafeSearchTool()

# ---------------------------------------------------------------------------
# Per-agent iteration budgets
# ---------------------------------------------------------------------------
# Per-agent iteration budgets — kept tight to minimise LLM calls on the
# Groq free tier (30 RPM / 6000 TPM per minute).
_RESEARCHER_MAX_ITER = 2   # 1 search + 1 summary
_ANALYST_MAX_ITER   = 1   # single-pass extraction + fact-check combined
_WRITER_MAX_ITER    = 1   # one shot — no tools needed
_DEFAULT_MAX_ITER   = 1   # coordinator — single pass

# 5 agents sharing a single 12k TPM bucket on Groq's free tier.
# Each agent is allowed at most 2 RPM to prevent burst exhaustion.
_AGENT_MAX_RPM = 2

# Inter-agent sleep (seconds) injected between sequential task completions.
# Groq's TPM window resets every 60 s.  Spreading 5 agent invocations across
# the minute keeps per-window token usage well under the 12k limit.
# Coordinator + Researcher burn the most tokens (tool schemas + search results);
# Analyst/Fact-Checker/Writer are text-only and cheaper.
_INTER_AGENT_SLEEP = 8   # seconds between consecutive agent completions

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Crew factory — called fresh for every run to avoid the CrewAI
# "Executor is already running" error that occurs when a module-level
# singleton crew is reused across concurrent or back-to-back requests.
# LLM objects (llm, _researcher_llm) are still module-level because they
# are stateless and cheap to share.
# ---------------------------------------------------------------------------

def _build_crew(run_id: str) -> tuple:
    """Return (crew, task_stage_map) with brand-new Agent/Task/Crew instances."""

    # ── Agents ──────────────────────────────────────────────────────────────
    _coordinator = Agent(
        role="Coordinator",
        goal="Plan the competitive-intelligence briefing sections.",
        backstory="Senior project manager. Never write content — only produce a concise plan.",
        allow_delegation=False,
        verbose=False,
        llm=llm,
        max_iter=_DEFAULT_MAX_ITER,
        max_rpm=_AGENT_MAX_RPM,
    )

    _researcher = Agent(
        role="Researcher",
        goal=(
            f"Run up to {settings.max_sources} web searches on the topic. "
            "Find AT LEAST 6 distinct named competitor companies. "
            "For every finding, include the exact URL from the search result as a citation [Source Name](https://...)."
        ),
        backstory=(
            "Expert competitive intelligence researcher. You search broadly to find MANY competitors — "
            "never stop at 1-2. You always cite sources with the real URL from the search result."
        ),
        tools=[_search_tool],
        allow_delegation=False,
        verbose=False,
        llm=_researcher_llm,
        max_iter=_RESEARCHER_MAX_ITER,
        max_retry_limit=2,
        max_rpm=_AGENT_MAX_RPM,
    )

    _analyst = Agent(
        role="Analyst",
        goal=(
            "Extract claims from research AND verify each one in a single pass. "
            "Cover AT LEAST 5 named competitors with specific pricing/product/market facts. "
            "Every claim MUST have an inline citation [Source Name](https://real-url). "
            "Prefix any claim that has no source URL with [UNVERIFIED]."
        ),
        backstory=(
            "Fast, precise market analyst and fact-checker combined. "
            "You read raw research once, extract verified claims with real URLs, "
            "and flag anything unsupported — all in one pass."
        ),
        allow_delegation=False,
        verbose=False,
        llm=_analyst_llm,
        max_iter=_ANALYST_MAX_ITER,
        max_rpm=_AGENT_MAX_RPM,
    )

    _fact_checker = Agent(
        role="Fact-Checker",
        goal="Cross-check every Analyst claim against raw research. Flag uncited claims as [UNVERIFIED].",
        backstory="Meticulous fact-checker. Only verify — do not add new information.",
        allow_delegation=False,
        verbose=False,
        llm=_analyst_llm,
        max_iter=_DEFAULT_MAX_ITER,
        max_rpm=_AGENT_MAX_RPM,
    )

    _writer = Agent(
        role="Writer",
        goal=(
            "Write the final briefing with exactly 3 sections covering AT LEAST 6 competitors. "
            "Every bullet MUST end with [Source Name](https://real-url-from-research.com) — "
            "use the real URLs from the research, never placeholder text."
        ),
        backstory=(
            "Business writer specialising in concise competitive intelligence reports. "
            "You write comprehensive reports covering many competitors and always use "
            "real source URLs in your citations."
        ),
        allow_delegation=False,
        verbose=False,
        llm=llm,
        max_iter=_WRITER_MAX_ITER,
        max_rpm=_AGENT_MAX_RPM,
    )

    # ── Tasks ────────────────────────────────────────────────────────────────
    _planning_task = Task(
        description=(
            "Plan a competitive-intelligence briefing on: {topic}\n"
            "Output a brief bullet-point outline for exactly 3 sections:\n"
            "1. Executive Summary  2. Competitor Pricing & Product Moves  3. Market Signals\n"
            "The briefing must cover AT LEAST 6 named competitors with specific data points."
        ),
        expected_output="A short bullet-point outline for the 3 sections, listing 6+ competitor names to cover.",
        agent=_coordinator,
    )

    _research_task = Task(
        description=(
            f"Search for {{topic}} using the search tool. Run at most {settings.max_sources} searches then stop.\n"
            "IMPORTANT: Find AT LEAST 6 different named competitor companies with specific facts.\n"
            "For each finding, format citations as: [Company Name or Publication](https://exact-url-from-search-result)\n"
            "Always use the actual URL from the search result — never write 'url' as a placeholder.\n"
            "Report findings as bullet points: each bullet ends with [Source](https://url)"
        ),
        expected_output=(
            "Bullet-point findings covering 6+ named competitors, each bullet ending with "
            "[Source Name](https://real-url.com) using the actual URL from the search results."
        ),
        agent=_researcher,
        context=[_planning_task],
    )

    _analyze_task = Task(
        description=(
            "Read the research findings and in ONE pass:\n"
            "1. Group claims into 3 sections: Executive Summary, Competitor Pricing & Product Moves, Market Signals\n"
            "2. For each claim copy the exact citation URL from the research: [Source Name](https://real-url)\n"
            "3. Prefix any claim with NO source URL with [UNVERIFIED]\n"
            "Cover at least 5 named competitors. Be concise — 3-4 claims per section max."
        ),
        expected_output=(
            "Three sections with cited claims. Each claim ends with [Source](https://url). "
            "Unsourced claims prefixed [UNVERIFIED]."
        ),
        agent=_analyst,
        context=[_research_task],
    )

    _fact_check_task = Task(
        description=(
            "Quick pass: confirm every claim from the Analyst has a citation URL. "
            "If any claim is missing a URL, prefix it [UNVERIFIED]. "
            "Do NOT rewrite claims — only add [UNVERIFIED] where needed. "
            "Output the same 3-section structure unchanged."
        ),
        expected_output="Same 3-section list, [UNVERIFIED] added to any claim missing a URL.",
        agent=_fact_checker,
        context=[_research_task, _analyze_task],
    )

    _write_task = Task(
        description=(
            "Write the final briefing. Output markdown with EXACTLY these headings:\n\n"
            "## Executive Summary\n## Competitor Pricing & Product Moves\n## Market Signals\n\n"
            "Rules:\n"
            "- 3-5 bullet points per section\n"
            "- Every bullet MUST end with [Source Name](https://real-url-from-research)\n"
            "  Example: [TechCrunch](https://techcrunch.com/2025/06/article)\n"
            "  NEVER write placeholder URLs like (url) or (link)\n"
            "- Executive Summary must include a '- **Recommendation:**' bullet\n"
            "- Skip any [UNVERIFIED] claims\n"
            "- No preamble or closing remarks\n\n"
            "Topic: {topic}"
        ),
        expected_output=(
            "Markdown briefing: 3 ## sections, 3-5 bullets each, "
            "every bullet ending with [Source](https://real-url)."
        ),
        agent=_writer,
        context=[_fact_check_task],
    )

    # ── Crew ─────────────────────────────────────────────────────────────────
    _crew = Crew(
        agents=[_coordinator, _researcher, _analyst, _fact_checker, _writer],
        tasks=[_planning_task, _research_task, _analyze_task, _fact_check_task, _write_task],
        process=Process.sequential,
        verbose=False,
        max_rpm=5,
        max_execution_time=MAX_EXECUTION_SECONDS,
    )

    _task_stage_map = [
        (_planning_task,    "Coordinator"),
        (_research_task,    "Researcher"),
        (_analyze_task,     "Analyst"),
        (_fact_check_task,  "Fact-Checker"),
        (_write_task,       "Writer"),
    ]

    return _crew, _task_stage_map

# ---------------------------------------------------------------------------
# Output parser  (simple heading‑based splitter)
# ---------------------------------------------------------------------------

_SECTION_HEADING_PATTERN = re.compile(
    r"#{1,3}\s*(Executive Summary|Competitor Pricing\s*(?:&|and)\s*Product Moves|Market Signals)",
    re.IGNORECASE,
)


def _normalize_section_title(raw: str) -> str:
    """Map fuzzy heading matches back to the canonical controlled vocabulary."""
    raw_lower = raw.lower().strip()
    if "executive" in raw_lower:
        return "Executive Summary"
    if "competitor" in raw_lower or "pricing" in raw_lower or "product" in raw_lower:
        return "Competitor Pricing & Product Moves"
    if "market" in raw_lower or "signal" in raw_lower:
        return "Market Signals"
    return raw  # pass through — will fail schema validation and be caught


def _parse_sections(raw_text: str) -> List[Section]:
    """Split raw markdown into Section objects by recognised heading markers.

    For each section, the text below the heading is split into individual
    claims (by double newline or bullet point), and citation markers are
    extracted into structured Citation objects.
    """
    # Find all heading positions.
    matches = list(_SECTION_HEADING_PATTERN.finditer(raw_text))
    if not matches:
        # Fallback: treat the whole text as a single section if nothing
        # matched (graceful degradation).
        return []

    sections: List[Section] = []
    for i, match in enumerate(matches):
        title = _normalize_section_title(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        body = raw_text[start:end].strip()

        # Split body into candidate claims — on blank lines or bullet lines.
        raw_claims = _split_claims(body)
        claims: List[Claim] = []
        for rc in raw_claims:
            if not rc.strip():
                continue
            citations = extract_citations(rc)
            clean_text = strip_citation_markers(rc)
            if clean_text:
                claims.append(
                    Claim(text=clean_text, citations=citations, verified=bool(citations))
                )

        sections.append(Section(title=title, claims=claims))

    return sections


def _split_claims(body: str) -> List[str]:
    """Split a section body into claim‑sized blocks.

    Prefers splitting on markdown bullet lines (- , *) or numbered lines;
    falls back to double‑newline blocks.
    """
    lines = body.split("\n")
    blocks: List[str] = []
    current: List[str] = []

    for line in lines:
        stripped = line.strip()
        # A new bullet or numbered line starts a new claim.
        if stripped.startswith("- ") or stripped.startswith("* ") or re.match(r"^\d+[.)]\s", stripped):
            if current:
                blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    # If nothing was split (e.g. plain paragraphs), fall back to
    # double‑newline separation.
    if not blocks:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]

    return blocks


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_briefing(topic: str, triggered_by: str = "manual") -> Briefing:
    """Execute a full competitive‑intelligence crew run for *topic*.

    Parameters
    ----------
    topic:
        The market / competitive topic to research.
    triggered_by:
        Either ``"manual"`` (user-submitted via the API) or
        ``"scheduled"`` (fired by the weekly APScheduler job).
        Stored in RunMetadata so the UI and audit log can distinguish
        automated reports from ad-hoc analyst requests.

    Handles every failure path so the caller (e.g. a FastAPI route) always
    receives a well‑formed Briefing object, never an exception.
    """
    run_id = str(uuid4())
    started_at = datetime.utcnow()

    # Reset the shared search tool counters so each run starts fresh.
    # (The tool is a module-level singleton reused across runs.)
    _search_tool.search_count = 0
    _search_tool.skipped_sources = []
    # PHASE 2: also reset cache hit counter
    try:
        _search_tool.cache_hits = 0
    except Exception:
        pass

    metadata = RunMetadata(
        run_id=run_id,
        topic=topic,
        started_at=started_at,
        status="running",
        triggered_by=triggered_by,  # type: ignore[arg-type]
    )

    # ---- PHASE 1: initialise stage registry for this run -----------------
    # Pre-populate all 5 stages as 'pending' so the frontend stepper can show
    # all nodes immediately, before any stage has started.
    try:
        _stage_registry[run_id] = [
            {
                "stage_name":   name,
                "status":       "pending",
                "description":  desc,
                "started_at":   None,
                "completed_at": None,
            }
            for name, desc in _STAGE_DEFS
        ]
    except Exception:
        pass  # stage tracking must never crash the run

    try:
        # ---- Kick off the crew (with 429 retry logic) ---------------------
        # Retry up to 2 times on rate-limit errors with a short fixed delay.
        # litellm.num_retries=3 handles lower-level retries; this outer loop
        # handles full crew-kickoff level 429s that slip through.

        # ---- Build a fresh crew for this run --------------------------------
        # A module-level singleton crew causes "Executor is already running"
        # on back-to-back or concurrent requests. Build new instances here.
        crew, _TASK_STAGE_MAP = _build_crew(run_id)
        _stage_desc_map = dict(_STAGE_DEFS)

        # Attach after-completion callbacks to each task (CrewAI Task supports
        # a `callback` kwarg that fires with the task output when done).
        # Use a closure to capture run_id and stage name safely.
        # We also inject a blocking sleep here to spread consecutive agent
        # invocations across Groq's 60-second TPM window.  The callback runs
        # synchronously inside CrewAI's sequential executor, so time.sleep()
        # is correct (asyncio.sleep would require an event loop we don't own).
        def _make_stage_callback(r_id: str, s_name: str):
            import time
            def _cb(output):  # noqa: ANN001
                try:
                    _stage_end(r_id, s_name, "done")
                except Exception:
                    pass
                # Don't sleep after the final Writer stage — run is done.
                if s_name != "Writer":
                    try:
                        time.sleep(_INTER_AGENT_SLEEP)
                    except Exception:
                        pass
            return _cb

        try:
            for task_obj, stage_nm in _TASK_STAGE_MAP:
                task_obj.callback = _make_stage_callback(run_id, stage_nm)
        except Exception:
            pass  # never block execution for stage tracking

        _MAX_RETRIES = 3  # litellm handles per-call 429s; this catches crew-level failures
        _attempt = 0
        result = None
        while True:
            try:
                # Reset any stale executor state from a previous failed run.
                # CrewAI reuses agent_executor if it exists (updating params
                # instead of creating fresh), so _is_executing can stay True
                # after a crash. Force-clear it before every attempt.
                try:
                    for _agent in crew.agents:
                        _exc = getattr(_agent, "agent_executor", None)
                        if _exc is not None:
                            _exc._is_executing = False
                            _exc._has_been_invoked = False
                except Exception:
                    pass

                # PHASE 1: mark Coordinator as running before kickoff
                try:
                    _stage_start(run_id, "Coordinator",
                                 _stage_desc_map.get("Coordinator", ""))
                except Exception:
                    pass

                result = await crew.kickoff_async(inputs={"topic": topic})
                break  # success — exit retry loop
            except Exception as _kick_exc:
                exc_str = str(_kick_exc)
                is_rate_limit = (
                    "429" in exc_str
                    or "rate_limit" in exc_str.lower()
                    or "RateLimitError" in exc_str
                )
                if is_rate_limit and _attempt < _MAX_RETRIES:
                    # Extract the actual retry-after from Groq's error body.
                    # Groq sends: "Please try again in 42.72s"
                    # We honour the full value (no cap) so we don't retry
                    # before the window has actually reset.
                    _ra = re.search(
                        r"(?:try again in|retry.?after)[^\d]*(\d+(?:\.\d+)?)\s*([smh]?)",
                        exc_str, re.IGNORECASE
                    )
                    if _ra:
                        _secs = float(_ra.group(1))
                        _unit = (_ra.group(2) or "s").lower()
                        if _unit == "m": _secs *= 60
                        elif _unit == "h": _secs *= 3600
                        _retry_after = int(_secs) + 5  # +5s buffer, no upper cap
                    else:
                        _retry_after = 65  # conservative default — one full minute
                    _attempt += 1
                    logger.warning(
                        "Rate-limited (429) on attempt %d/%d — waiting %ds before retry.",
                        _attempt, _MAX_RETRIES, _retry_after,
                    )
                    await asyncio.sleep(_retry_after)
                else:
                    # Not a rate-limit error, or out of retries — re-raise.
                    raise

        # crew.kickoff returns a CrewOutput; the final task's output is in
        # result.raw or can be accessed as a string.
        raw_output = str(result) if result else ""

        # PHASE 1: mark any stages that are still pending/running as done
        # (handles the 4 stages after Coordinator whose _stage_start we
        # couldn't inject without modifying the crew internals).
        try:
            for entry in _stage_registry.get(run_id, []):
                if entry["status"] in ("pending", "running"):
                    entry["status"] = "done"
                    if entry["started_at"] is None:
                        from datetime import timezone
                        entry["started_at"] = datetime.now(timezone.utc).isoformat()
                    if entry["completed_at"] is None:
                        from datetime import timezone
                        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        except Exception:
            pass

        # Guard: if the raw output looks like an exception traceback or rate-limit
        # error message, do not attempt to parse it as briefing content.
        # This prevents stack traces from becoming "claims" in the UI.
        _ERROR_SIGNALS = ("RateLimitError", "RateLimit", "GroqException", "Traceback", "litellm.")
        if any(sig in raw_output for sig in _ERROR_SIGNALS):
            raise RuntimeError(f"Crew output contains an error message: {raw_output[:300]}")

        # ---- Parse the writer's output into sections ----------------------
        sections = _parse_sections(raw_output)

        # Fallback: if parsing produced no sections or all sections are empty,
        # try to recover by treating the entire raw output as uncited claims
        # in a single "Executive Summary" section so the user sees *something*.
        # Only attempt this if the text looks like real content (has letters).
        total_claims = sum(len(s.claims) for s in sections)
        if (not sections or total_claims == 0) and raw_output.strip():
            fallback_claims = []
            for block in re.split(r"\n\s*\n", raw_output.strip()):
                block = block.strip()
                if not block:
                    continue
                # Skip blocks that are error messages or single-line noise
                if any(sig in block for sig in _ERROR_SIGNALS):
                    continue
                citations = extract_citations(block)
                clean = strip_citation_markers(block)
                if clean:
                    fallback_claims.append(
                        Claim(text=clean, citations=citations, verified=bool(citations))
                    )
            if fallback_claims:
                sections = [Section(title="Executive Summary", claims=fallback_claims)]

        # ---- Governance layer 1: drop uncited claims ----------------------
        sections, citation_flags = enforce_citations(sections, run_id=run_id)

        # ---- Governance layer 2: flag weakly‑sourced high‑risk claims -----
        sections, unverified_flags = flag_unverified_assertions(sections, run_id=run_id)

        # ---- Build metadata -----------------------------------------------
        ended_at = datetime.utcnow()
        duration = (ended_at - started_at).total_seconds()

        metadata.duration_seconds = duration
        metadata.sources_used = _search_tool.search_count
        metadata.sources_skipped = _search_tool.skipped_sources
        metadata.sources_attempted = _search_tool.search_count + len(_search_tool.skipped_sources)
        metadata.total_steps = MAX_STEPS
        # PHASE 2: surface cache_hits from the search tool in metadata
        try:
            metadata.cache_hits = getattr(_search_tool, "cache_hits", 0)
        except Exception:
            pass  # never break on new fields

        # ---- KPI 1: % of claims cited (SPEC.md §3) -----------------------
        # Count after governance has run so the percentage reflects the final
        # briefing state seen by the reviewer, not the raw pre-governance output.
        # FR-4 guarantees all surviving claims have citations, so this should
        # always be 100.0 — making it explicit surfaces that guarantee visibly.
        all_claims_after_gov = [c for s in sections for c in s.claims]
        _total = len(all_claims_after_gov)
        _cited = sum(1 for c in all_claims_after_gov if c.citations)
        metadata.cited_claims_pct = round(_cited / _total * 100, 1) if _total > 0 else None

        # Internal state after the crew finishes is "completed"; the
        # governance checks have now run so we transition to
        # "pending_review" — a human must approve before "published".
        metadata.status = "pending_review"

        return Briefing(
            metadata=metadata,
            sections=sections,
            unverified_flags=citation_flags + unverified_flags,
        )

    except Exception as exc:
        # ---- Graceful degradation on any failure -------------------------
        # WHY: The API layer (FastAPI) must never return a 500 because a
        # crew run failed.  Instead we return a partial Briefing with
        # status="failed" and whatever metadata we have.
        ended_at = datetime.utcnow()
        duration = (ended_at - started_at).total_seconds()

        metadata.duration_seconds = duration
        metadata.sources_used = _search_tool.search_count
        metadata.sources_skipped = _search_tool.skipped_sources
        metadata.sources_attempted = _search_tool.search_count + len(_search_tool.skipped_sources)
        metadata.total_steps = MAX_STEPS
        metadata.status = "failed"

        # PHASE 1: mark any still-running/pending stages as failed
        try:
            for entry in _stage_registry.get(run_id, []):
                if entry["status"] in ("pending", "running"):
                    entry["status"] = "failed"
        except Exception:
            pass

        # ---- Map exception to a human-readable message -------------------
        exc_str = str(exc)
        # Determine which provider is configured so error messages are accurate
        _model = settings.model_name.lower()
        if _model.startswith("gemini") or "google" in _model:
            _provider = "gemini"
        elif _model.startswith("groq"):
            _provider = "groq"
        elif _model.startswith("openrouter"):
            _provider = "openrouter"
        else:
            _provider = "groq"  # default fallback

        _provider_links = {
            "gemini": "https://ai.dev/rate-limit",
            "groq": "https://console.groq.com",
            "openrouter": "https://openrouter.ai/settings",
        }
        _provider_link = _provider_links.get(_provider, "https://console.groq.com")
        _provider_label = _provider.capitalize()

        is_rate_limit = (
            "429" in exc_str
            or "rate_limit" in exc_str.lower()
            or "RateLimitError" in exc_str
        )
        is_invalid_key = (
            "401" in exc_str
            or "invalid_api_key" in exc_str.lower()
            or "invalid api key" in exc_str.lower()
            or "authentication" in exc_str.lower()
        )
        if is_rate_limit:
            # Try to extract the retry-after seconds from the error body
            _ra_match = re.search(
                r"(?:retry[_\-]after|please try again in)[\":\s]+(\d+(?:\.\d+)?)",
                exc_str, re.IGNORECASE
            )
            _wait = f"~{int(float(_ra_match.group(1)))}s" if _ra_match else "~60s"
            human_error = (
                f"{_provider_label} rate limit reached (retry after {_wait}). "
                "The free tier allows limited requests per minute. "
                f"Wait a moment and try again, or check your quota at {_provider_link}."
            )
        elif "402" in exc_str:
            human_error = f"{_provider_label} billing issue. Check your account at {_provider_link}."
        elif is_invalid_key:
            human_error = (
                f"Invalid {_provider_label} API key. "
                f"Open your .env file and set a real API key: "
                f"GROQ_API_KEY=gsk_...  — get yours at {_provider_link}."
            )
        elif "404" in exc_str and ("model" in exc_str.lower() or "endpoints" in exc_str.lower()):
            human_error = (
                f"Model not found on {_provider_label}. "
                f"Check MODEL_NAME in .env — current value: {settings.model_name}."
            )
        elif "failed to call a function" in exc_str.lower() or "failed_generation" in exc_str.lower():
            human_error = (
                "Model failed to generate a valid tool call. "
                "Restart the backend and try again."
            )
        elif "Crew output contains an error message" in exc_str:
            # Our own guard raised — the inner message is already clean-ish
            human_error = exc_str.replace("Crew output contains an error message: ", "")[:200]
            # Re-map if it's still a rate-limit string
            if "RateLimitError" in human_error or "rate_limit" in human_error.lower():
                human_error = (
                    f"{_provider_label} rate limit reached. "
                    f"Wait a moment and try again, or check your quota at {_provider_link}."
                )
        else:
            # Include the first 300 chars of the raw exception so it surfaces
            # in the UI — makes diagnosis possible without server log access.
            human_error = f"Run failed: {exc_str[:300]}"

        return Briefing(
            metadata=metadata,
            sections=[],
            unverified_flags=[human_error],
        )
