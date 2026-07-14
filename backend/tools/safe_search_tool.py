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
import warnings
from typing import List

import requests

# crewai_tools.BaseTool uses an old-style Pydantic v1 `class Config` block
# internally.  This is a third-party library issue and not actionable from our
# code; suppress the warning so it doesn't pollute server logs or test output.
warnings.filterwarnings(
    "ignore",
    message="Support for class-based `config` is deprecated",
    category=DeprecationWarning,
)

from crewai_tools import BaseTool


class SafeSearchTool(BaseTool):
    """A search tool with a per-instance call limit and exception safety.

    Uses the Serper API directly instead of wrapping SerperDevTool, because
    SerperDevTool._run() has incompatible argument handling in some versions.

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

    def _run(self, query: str, **kwargs) -> str:
        """Execute a search, subject to the runaway source cap.

        Returns the search results text, or a refusal / error message.
        Never raises.
        """
        max_sources = int(os.getenv("MAX_SOURCES", "15"))
        api_key = os.getenv("SERPER_API_KEY")

        # ---- Runaway guard -------------------------------------------------
        if self.search_count >= max_sources:
            msg = (
                f"[SafeSearchTool] Source cap of {max_sources} reached. "
                f"Skipping query: '{query}'"
            )
            self.skipped_sources.append(query)
            return msg

        if not api_key:
            self.skipped_sources.append(query)
            return f"[SafeSearchTool] No SERPER_API_KEY configured. Skipping query: '{query}'"

        # ---- Make the real call, wrapped in a shield -----------------------
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                json={"q": query},
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            # Format results for the LLM agent
            results = []
            for item in data.get("organic", []):
                title = item.get("title", "")
                link = item.get("link", "")
                snippet = item.get("snippet", "")
                results.append(f"- {title}\n  {link}\n  {snippet}")

            self.search_count += 1
            return "\n\n".join(results) if results else f"[SafeSearchTool] No results found for: '{query}'"

        except Exception as exc:
            self.skipped_sources.append(query)
            # Give a more actionable message for 403 (invalid/expired Serper key)
            if "403" in str(exc):
                return (
                    f"[SafeSearchTool] Serper API key is invalid or unauthorized (403). "
                    f"Get a valid key at https://serper.dev and set SERPER_API_KEY in .env. "
                    f"Skipping query: '{query}'"
                )
            return (
                f"[SafeSearchTool] Source unreachable, skipped. "
                f"Query: '{query}' -- {exc}"
            )
