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
import time
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

# Configure litellm for Groq free-tier — keep retries low so a rate-limited
# run fails fast rather than stacking 60s waits across 3 internal retries.
# The outer retry loop in run_briefing() handles the meaningful retries.
litellm.num_retries = 1
litellm.request_timeout = 30

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
    model=settings.model_name,          # text-only agents (coordinator, analyst, etc.)
    api_key=settings.llm_api_key,       # correct key for whatever provider is configured
    max_tokens=settings.max_tokens,
)

# For the researcher we use llama-3.1-8b-instant on Groq (handles JSON tool
# calls reliably). If the main model is already 8b-instant, reuse it directly.
_researcher_model = (
    "groq/llama-3.1-8b-instant"
    if settings.provider == "groq"
    else settings.model_name
)
_researcher_llm = LLM(
    model=_researcher_model,
    api_key=settings.llm_api_key,
    max_tokens=300,   # researcher only needs short tool calls + a brief summary
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
_RESEARCHER_MAX_ITER = 2   # 1 search + 1 summary is enough
_WRITER_MAX_ITER = 1       # one shot — no tools needed
_DEFAULT_MAX_ITER = 1      # coordinator, analyst, fact-checker — single pass

# Agent-level RPM cap — 5 agents sharing 30 RPM = 6 each, use 5 to be safe
_AGENT_MAX_RPM = 5

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

coordinator = Agent(
    role="Coordinator",
    goal="Plan the competitive-intelligence briefing sections.",
    backstory="Senior project manager. Never write content — only produce a concise plan.",
    allow_delegation=False,
    verbose=False,
    llm=llm,
    max_iter=_DEFAULT_MAX_ITER,
    max_rpm=_AGENT_MAX_RPM,
)

researcher = Agent(
    role="Researcher",
    goal=f"Run up to {settings.max_sources} web searches on the topic, then stop and report findings with inline citations.",
    backstory="Focused web researcher. Run targeted searches, compile findings with citations, then stop.",
    tools=[_search_tool],
    allow_delegation=False,
    verbose=False,
    llm=_researcher_llm,
    max_iter=_RESEARCHER_MAX_ITER,
    max_retry_limit=1,
    max_rpm=_AGENT_MAX_RPM,
)

analyst = Agent(
    role="Analyst",
    goal="Extract and classify claims from research. Distinguish verified facts from single-source rumors.",
    backstory="Sharp market analyst. Read raw research, produce citable claims, flag uncertainty.",
    allow_delegation=False,
    verbose=False,
    llm=llm,
    max_iter=_DEFAULT_MAX_ITER,
    max_rpm=_AGENT_MAX_RPM,
)

fact_checker = Agent(
    role="Fact-Checker",
    goal="Cross-check every Analyst claim against raw research. Flag uncited claims as [UNVERIFIED].",
    backstory="Meticulous fact-checker. Only verify — do not add new information.",
    allow_delegation=False,
    verbose=False,
    llm=llm,
    max_iter=_DEFAULT_MAX_ITER,
    max_rpm=_AGENT_MAX_RPM,
)

writer = Agent(
    role="Writer",
    goal="Write the final briefing with exactly 3 sections. Every bullet must end with [Source](url).",
    backstory="Business writer specialising in concise competitive intelligence reports.",
    allow_delegation=False,
    verbose=False,
    llm=llm,
    max_iter=_WRITER_MAX_ITER,
    max_rpm=_AGENT_MAX_RPM,
)

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

planning_task = Task(
    description=(
        "Plan a competitive-intelligence briefing on: {topic}\n"
        "Output a brief bullet-point outline for exactly 3 sections:\n"
        "1. Executive Summary  2. Competitor Pricing & Product Moves  3. Market Signals"
    ),
    expected_output="A short bullet-point outline for the 3 sections.",
    agent=coordinator,
)

research_task = Task(
    description=(
        f"Search for {{topic}} using the search tool. Run at most {settings.max_sources} searches then stop.\n"
        "Report findings as bullet points with inline citations [Source](url)."
    ),
    expected_output="Bullet-point findings with inline citations [Source Name](url).",
    agent=researcher,
    context=[planning_task],
)

analyze_task = Task(
    description=(
        "Organise the research findings into 3 groups matching the briefing sections.\n"
        "Keep well-sourced claims as verified. Mark single-source items as uncertain.\n"
        "Each claim must have an inline citation [Source](url)."
    ),
    expected_output="Claims grouped by section with citations and confidence notes.",
    agent=analyst,
    context=[research_task],
)

fact_check_task = Task(
    description=(
        "Check each Analyst claim against the research. "
        "If a claim has no supporting source in the research, prefix it '[UNVERIFIED]'.\n"
        "Output the same 3-section structure with [UNVERIFIED] prefixes where needed."
    ),
    expected_output="Three-section claim list with [UNVERIFIED] on unsupported claims.",
    agent=fact_checker,
    context=[research_task, analyze_task],
)

write_task = Task(
    description=(
        "Write the final briefing using ONLY the verified findings. Output markdown with EXACTLY these headings:\n\n"
        "## Executive Summary\n## Competitor Pricing & Product Moves\n## Market Signals\n\n"
        "Rules: 3-5 bullet points per section. Every bullet MUST end with [Source](url).\n"
        "Executive Summary must include a '- **Recommendation:**' bullet.\n"
        "Skip any [UNVERIFIED] claims. No preamble or closing remarks.\n\n"
        "Topic: {topic}"
    ),
    expected_output=(
        "Markdown briefing with 3 ## sections, each 3-5 bullets ending with [Source](url)."
    ),
    agent=writer,
    context=[fact_check_task],
)

# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------
# FIX 1: max_rpm=20 at crew level enforces a global call rate ceiling.
# FIX 2: All 5 agents/tasks included in the correct sequential order.

crew = Crew(
    agents=[coordinator, researcher, analyst, fact_checker, writer],
    tasks=[planning_task, research_task, analyze_task, fact_check_task, write_task],
    process=Process.sequential,
    verbose=True,
    max_rpm=5,   # crew-level ceiling — 5 agents × 5 RPM each = 25 RPM total, under 30 RPM free tier
    max_execution_time=MAX_EXECUTION_SECONDS,
)

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

        # PHASE 1: Register stage callbacks on each task so we can track
        # progress without changing the crew's sequential logic.
        # Each task callback fires AFTER the task completes — we pair it with
        # a _stage_start call injected before kickoff via a mapping.
        _TASK_STAGE_MAP = [
            (planning_task,    "Coordinator"),
            (research_task,    "Researcher"),
            (analyze_task,     "Analyst"),
            (fact_check_task,  "Fact-Checker"),
            (write_task,       "Writer"),
        ]
        _stage_desc_map = dict(_STAGE_DEFS)

        # Attach after-completion callbacks to each task (CrewAI Task supports
        # a `callback` kwarg that fires with the task output when done).
        # Use a closure to capture run_id and stage name safely.
        def _make_stage_callback(r_id: str, s_name: str):
            def _cb(output):  # noqa: ANN001
                try:
                    _stage_end(r_id, s_name, "done")
                except Exception:
                    pass
                # Brief pause after heavy agents to let the Groq TPM window
                # breathe before the next agent fires.
                if s_name in ("Researcher", "Analyst", "Fact-Checker"):
                    time.sleep(5)
            return _cb

        try:
            for task_obj, stage_nm in _TASK_STAGE_MAP:
                task_obj.callback = _make_stage_callback(run_id, stage_nm)
        except Exception:
            pass  # never block execution for stage tracking

        _MAX_RETRIES = 2
        _attempt = 0
        result = None
        while True:
            try:
                # PHASE 1: mark Coordinator as running before kickoff
                # (CrewAI runs tasks sequentially, so Coordinator is first)
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
                    # Extract the actual retry-after from the error message
                    _ra = re.search(
                        r"(?:try again in|retry.?after)[^\d]*(\d+(?:\.\d+)?)\s*([smh]?)",
                        exc_str, re.IGNORECASE
                    )
                    if _ra:
                        _secs = float(_ra.group(1))
                        _unit = (_ra.group(2) or "s").lower()
                        if _unit == "m": _secs *= 60
                        elif _unit == "h": _secs *= 3600
                        _retry_after = min(int(_secs) + 2, 65)  # cap at 65s
                    else:
                        _retry_after = 30
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
        elif "404" in exc_str and ("model" in exc_str.lower() or "endpoints" in exc_str.lower()):
            human_error = (
                f"Model not found on {_provider_label}. "
                f"Check MODEL_NAME in .env — current value: {settings.model_name}."
            )
        elif "401" in exc_str:
            human_error = (
                f"Invalid {_provider_label} API key. "
                f"Check your API key in .env and verify it at {_provider_link}."
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
