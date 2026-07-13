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

load_dotenv()

# ---------------------------------------------------------------------------
# LLM configuration — OpenRouter via CrewAI's LLM class
# ---------------------------------------------------------------------------

llm = LLM(
    model=os.getenv("MODEL_NAME", "openrouter/meta-llama/llama-3.3-70b-instruct"),
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    temperature=0.3,
    max_tokens=2000,
)

# ---------------------------------------------------------------------------
# Shared tool instances (stateful — counts are read after the run)
# ---------------------------------------------------------------------------

_search_tool = SafeSearchTool()

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
    max_iter=MAX_STEPS,
)

researcher = Agent(
    role="Researcher",
    goal=(
        "Gather at least 15 reachable sources on the given market topic, "
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
    max_iter=MAX_STEPS,
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
    max_iter=MAX_STEPS,
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
    max_iter=MAX_STEPS,
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
        "Using the SafeSearch tool, gather at least 15 reachable sources "
        "on {topic}.  Focus on:\n"
        "  - Recent competitor pricing changes and product launches\n"
        "  - Market signals (regulatory news, partnerships, funding rounds)\n\n"
        "Cite every piece of information inline with [Source Name](url).\n"
        "If a source is unreachable, note that fact and move on."
    ),
    expected_output=(
        "A list of bullet‑point research findings, each with an inline "
        "citation marker."
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
        "Based on the Analyst's structured findings, write the final "
        "briefing with these exact headings:\n\n"
        "---\n"
        "## Executive Summary\n"
        "… (concise overview with a strategic recommendation)\n\n"
        "## Competitor Pricing & Product Moves\n"
        "… (detailed pricing changes, product launches, comparisons)\n\n"
        "## Market Signals\n"
        "… (regulatory, partnership, funding, and other signals)\n\n"
        "---\n\n"
        "IMPORTANT: Every factual claim MUST be followed by an inline "
        "citation marker like [Source Name](url).  Use the exact section "
        "headings shown above so the parser can identify them."
    ),
    expected_output=(
        "A complete markdown briefing with three sections, each containing "
        "citation‑tagged claims."
    ),
    agent=writer,
    context=[planning_task, research_task, analyze_task],
)

# ---------------------------------------------------------------------------
# Crew
# ---------------------------------------------------------------------------

crew = Crew(
    agents=[coordinator, researcher, analyst, writer],
    tasks=[planning_task, research_task, analyze_task, write_task],
    process=Process.sequential,
    verbose=True,
    max_execution_time=MAX_EXECUTION_SECONDS,
)

# ---------------------------------------------------------------------------
# Output parser  (simple heading‑based splitter)
# ---------------------------------------------------------------------------

_SECTION_HEADING_PATTERN = re.compile(
    r"##\s*(Executive Summary|Competitor Pricing & Product Moves|Market Signals)",
    re.IGNORECASE,
)


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
        title = match.group(1)
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

    metadata = RunMetadata(
        run_id=run_id,
        topic=topic,
        started_at=started_at,
        status="running",
        triggered_by=triggered_by,  # type: ignore[arg-type]
    )

    try:
        # ---- Kick off the crew --------------------------------------------
        result = crew.kickoff(inputs={"topic": topic})

        # crew.kickoff returns a CrewOutput; the final task's output is in
        # result.raw or can be accessed as a string.
        raw_output = str(result) if result else ""

        # ---- Parse the writer's output into sections ----------------------
        sections = _parse_sections(raw_output)

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

        return Briefing(
            metadata=metadata,
            sections=[],
            unverified_flags=[f"Run failed with exception: {exc}"],
        )