"""
CrewAI crew for the Competitive Intelligence Briefing.

WHY THIS ARCHITECTURE EXISTS:
A single monolithic agent tends to produce shallow, poorly‑structured output.
By splitting the work across four specialised agents (coordinator → researcher
→ analyst → writer) we get:
  - **Coordinator** — plans the sections and hands off to each downstream agent.
  - **Researcher** — gathers raw web data (capped by SafeSearchTool's runaway guard).
  - **Analyst** — reasons over the research to extract signal from noise.
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
    model=settings.model_name,
    api_key=settings.groq_api_key,
    max_tokens=settings.max_tokens,
)
# ---------------------------------------------------------------------------
# Shared tool instances (stateful — counts are read after the run)
# ---------------------------------------------------------------------------

_search_tool = SafeSearchTool()

# ---------------------------------------------------------------------------
# Per-agent iteration budgets
# ---------------------------------------------------------------------------
# Researcher needs the most steps (it uses a tool in a ReAct loop).
# Coordinator, Analyst and Writer are pure text — they just need 1-3 calls.
_RESEARCHER_MAX_ITER = max(5, MAX_STEPS)
_WRITER_MAX_ITER = 3   # no tools; should produce output in a single LLM call
_DEFAULT_MAX_ITER = 5  # coordinator + analyst

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

coordinator = Agent(
    role="Coordinator",
    goal=(
        "Plan the competitive-intelligence briefing and ensure every "
        "section is produced in the correct order."
    ),
    backstory=(
        "You are a senior project manager who coordinates research and "
        "writing.  You never write content yourself, but you produce a "
        "clear plan that the Researcher, Analyst, and Writer agents follow."
    ),
    allow_delegation=False,
    verbose=True,
    llm=llm,
    max_iter=_DEFAULT_MAX_ITER,
)

researcher = Agent(
    role="Researcher",
    goal=(
        "Gather up to 8 reachable sources on the given market topic, "
        "covering pricing moves, product launches, and market signals."
    ),
    backstory=(
        "You are a tireless web researcher who uses search tools to find "
        "the most recent and relevant information on the topic.  You "
        "always cite your sources inline using [Source Name](url)."
    ),
    tools=[_search_tool],
    allow_delegation=False,
    verbose=True,
    llm=llm,
    max_iter=_RESEARCHER_MAX_ITER,
)

analyst = Agent(
    role="Analyst",
    goal=(
        "Compare and extract signal from the Researcher's raw findings. "
        "Produce well‑reasoned claims with proper citations, distinguishing "
        "verified facts from single‑source rumors."
    ),
    backstory=(
        "You are a sharp financial and market analyst who reads through "
        "raw research and distills it into clear, citable claims.  You "
        "flag uncertainty and avoid over‑stating weak evidence."
    ),
    allow_delegation=False,
    verbose=True,
    llm=llm,
    max_iter=_DEFAULT_MAX_ITER,
)

writer = Agent(
    role="Writer",
    goal=(
        "Produce the final structured briefing with three clearly headed "
        "sections: Executive Summary (with a recommendation), Competitor "
        "Pricing & Product Moves, and Market Signals.  Every claim must "
        "carry inline citation markers like [Source Name](url)."
    ),
    backstory=(
        "You are a seasoned business writer who specialises in concise, "
        "well‑structured competitive intelligence reports.  You never "
        "make a factual claim without attaching a citation marker."
    ),
    allow_delegation=False,
    verbose=True,
    llm=llm,
    max_iter=_WRITER_MAX_ITER,
)

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

planning_task = Task(
    description=(
        "Plan a competitive-intelligence briefing on the topic: {topic}.\n\n"
        "Output a list of sections that must be produced.  Do NOT write "
        "content — just a bullet‑point outline of what each section should "
        "contain.  The final briefing will have exactly three sections:\n"
        "  1. Executive Summary\n"
        "  2. Competitor Pricing & Product Moves\n"
        "  3. Market Signals"
    ),
    expected_output=(
        "A bullet‑point plan outlining the content needed for each of the "
        "three sections."
    ),
    agent=coordinator,
)

research_task = Task(
    description=(
        "Using the SafeSearch tool, gather up to 8 reachable sources "
        "on {topic}.  Focus on:\n"
        "  - Recent competitor pricing changes and product launches\n"
        "  - Market signals (regulatory news, partnerships, funding rounds)\n\n"
        "Run 4-6 searches, then STOP and report your findings.\n"
        "Cite every piece of information inline with [Source Name](url).\n"
        "If a source is unreachable, note that fact and move on."
    ),
    expected_output=(
        "A concise list of bullet‑point research findings (max 20 bullets), "
        "each with an inline citation marker."
    ),
    agent=researcher,
    context=[planning_task],
)

analyze_task = Task(
    description=(
        "Review the raw research provided by the Researcher.  For each "
        "finding:\n"
        "  - If it is well‑sourced (multiple citations or a major outlet), "
        "keep it as a verified claim.\n"
        "  - If it is a single‑source rumor, note the uncertainty.\n\n"
        "Organise findings into three groups matching the briefing sections."
    ),
    expected_output=(
        "Organised claims grouped by section, each with inline citation "
        "markers and a note on confidence level."
    ),
    agent=analyst,
    context=[planning_task, research_task],
)

write_task = Task(
    description=(
        "Using the Analyst's structured findings, write the final briefing NOW.\n"
        "Do not search for more information. Do not ask questions. Just write.\n\n"
        "Output ONLY the briefing markdown using these EXACT headings:\n\n"
        "## Executive Summary\n"
        "## Competitor Pricing & Product Moves\n"
        "## Market Signals\n\n"
        "Rules:\n"
        "1. Use EXACTLY those three ## headings, nothing else as a top-level heading.\n"
        "2. Under each heading, write 3-5 bullet points starting with '- '.\n"
        "3. Every bullet point MUST end with at least one citation: "
        "[Source Name](https://url)\n"
        "4. The Executive Summary must end with a '- **Recommendation:**' bullet.\n"
        "5. Keep each bullet to 1-2 sentences. Do not add preamble or closing remarks.\n\n"
        "Topic: {topic}"
    ),
    expected_output=(
        "A complete briefing with exactly three ## sections, each containing "
        "3-5 bullet points, every bullet ending with [Source Name](url). "
        "Nothing else — no intro text, no closing remarks."
    ),
    agent=writer,
    context=[analyze_task],
)

# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------

crew = Crew(
    agents=[coordinator, researcher, analyst, writer],
    tasks=[planning_task, research_task, analyze_task, write_task],
    process=Process.sequential,
    verbose=True,
    max_rpm=10,  # cap LLM calls/minute to avoid Groq rate limits
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

    metadata = RunMetadata(
        run_id=run_id,
        topic=topic,
        started_at=started_at,
        status="running",
        triggered_by=triggered_by,  # type: ignore[arg-type]
    )

    try:
        # ---- Kick off the crew (with 429 retry logic) ---------------------
        # Retry up to 2 times on rate-limit errors with exponential backoff.
        _MAX_RETRIES = 2
        _attempt = 0
        result = None
        while True:
            try:
                result = await crew.kickoff_async(inputs={"topic": topic})
                break  # success — exit retry loop
            except Exception as _kick_exc:
                exc_str = str(_kick_exc)
                if "429" in exc_str and _attempt < _MAX_RETRIES:
                    # Parse retry_after from the exception message if present.
                    _retry_match = re.search(r"retry[_\-]after[\":\s]+(\d+)", exc_str, re.IGNORECASE)
                    _retry_after = int(_retry_match.group(1)) if _retry_match else 30
                    _attempt += 1
                    logger.warning(
                        "Rate-limited (429) on attempt %d/%d — waiting %ds before retry.",
                        _attempt, _MAX_RETRIES, _retry_after,
                    )
                    await asyncio.sleep(_retry_after)
                else:
                    # Not a 429, or out of retries — re-raise to the outer handler.
                    raise

        # crew.kickoff returns a CrewOutput; the final task's output is in
        # result.raw or can be accessed as a string.
        raw_output = str(result) if result else ""

        # ---- Parse the writer's output into sections ----------------------
        sections = _parse_sections(raw_output)

        # Fallback: if parsing produced no sections or all sections are empty,
        # try to recover by treating the entire raw output as uncited claims
        # in a single "Executive Summary" section so the user sees *something*.
        total_claims = sum(len(s.claims) for s in sections)
        if not sections or total_claims == 0:
            fallback_claims = []
            for block in re.split(r"\n\s*\n", raw_output.strip()):
                block = block.strip()
                if block:
                    citations = extract_citations(block)
                    clean = strip_citation_markers(block)
                    if clean:
                        fallback_claims.append(
                            Claim(text=clean, citations=citations, verified=bool(citations))
                        )
            if fallback_claims:
                sections = [Section(title="Executive Summary", claims=fallback_claims)]

        # ---- Governance layer 1: drop uncited claims ----------------------
        sections, citation_flags = enforce_citations(sections)

        # ---- Governance layer 2: flag weakly‑sourced high‑risk claims -----
        sections, unverified_flags = flag_unverified_assertions(sections)

        # ---- Build metadata -----------------------------------------------
        ended_at = datetime.utcnow()
        duration = (ended_at - started_at).total_seconds()

        metadata.duration_seconds = duration
        metadata.sources_used = _search_tool.search_count
        metadata.sources_skipped = _search_tool.skipped_sources
        metadata.sources_attempted = _search_tool.search_count + len(_search_tool.skipped_sources)
        metadata.total_steps = MAX_STEPS
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

        # ---- Map exception to a human-readable message -------------------
        exc_str = str(exc)
        if "429" in exc_str and "rate_limit" in exc_str.lower():
            human_error = (
                "Groq rate limit reached. Free tier allows limited requests/minute. "
                "Wait a moment and try again, or check https://console.groq.com for limits."
            )
        elif "429" in exc_str:
            human_error = "Model is temporarily rate-limited. Please try again in 30 seconds."
        elif "402" in exc_str:
            human_error = "Groq billing issue. Check your account at https://console.groq.com"
        elif "404" in exc_str and ("model" in exc_str.lower() or "endpoints" in exc_str.lower()):
            human_error = "Model not found on Groq. Check MODEL_NAME in .env (e.g. groq/llama-3.3-70b-versatile)"
        elif "401" in exc_str:
            human_error = "Invalid Groq API key. Check GROQ_API_KEY in .env"
        else:
            human_error = exc_str[:200]

        return Briefing(
            metadata=metadata,
            sections=[],
            unverified_flags=[human_error],
        )
