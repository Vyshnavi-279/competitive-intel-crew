"""
SafeSearchTool — wraps SerperDevTool with a runaway-source guard.

WHY THIS GUARDRAIL EXISTS:
Without a cap, a CrewAI agent could send hundreds of search API calls in a
single run, racking up cost and potentially hitting rate limits.  The
runaway guard enforces a per-instance maximum (MAX_SOURCES from env,
default 15).  Once the limit is reached, further calls return a polite
refusal instead of making an HTTP request, and the crew run continues
gracefully.

Additionally, every underlying API call is wrapped in try/except so that
transient network issues or timeout errors never crash the entire crew run.
Skipped sources are recorded in self.skipped_sources so RunMetadata can
report them later.
"""

import os
from typing import List

from crewai_tools import BaseTool, SerperDevTool


class SafeSearchTool(BaseTool):
    """A search tool with a per-instance call limit and exception safety.

    Public attributes (read after the crew run):
        search_count   -- how many searches actually went through.
        skipped_sources -- list of query strings that failed or were refused.
    """

    name: str = "SafeSearch"
    description: str = (
        "Search the web for competitive intelligence. "
        "Each invocation counts toward a per-run source limit."
    )

    # Expose internals as public attributes so the crew/pipeline can read them.
    search_count: int = 0
    skipped_sources: List[str] = []

    # The real search engine underneath.
    _engine: SerperDevTool = SerperDevTool()

    def _run(self, query: str, **kwargs) -> str:
        """Execute a search, subject to the runaway source cap.

        Returns the search results text, or a refusal / error message.
        Never raises.
        """
        max_sources = int(os.getenv("MAX_SOURCES", "15"))

        # ---- Runaway guard -------------------------------------------------
        # If we've already hit the source cap, refuse the search instead of
        # making another API call.  This prevents unbounded cost/rate usage.
        if self.search_count >= max_sources:
            msg = (
                f"[SafeSearchTool] Source cap of {max_sources} reached. "
                f"Skipping query: '{query}'"
            )
            self.skipped_sources.append(query)
            return msg

        # ---- Make the real call, wrapped in a shield -----------------------
        try:
            result = self._engine.run(query, **kwargs)
            self.search_count += 1
            return result
        except Exception as exc:
            # Catch *everything* -- network timeout, API auth error, whatever.
            # The crew must never crash because a search failed.
            self.skipped_sources.append(query)
            return (
                f"[SafeSearchTool] Source unreachable, skipped. "
                f"Query: '{query}' -- {exc}"
            )