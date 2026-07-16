"""
SafeSearchTool — wraps the Serper API with a per-run source cap.

WHY THIS GUARDRAIL EXISTS:
Without a cap, a CrewAI agent could fire hundreds of search calls in one run.
The runaway guard enforces MAX_SOURCES (env var, default 15).  Once reached,
further calls return a STOP message so the agent knows to compile findings.
Every call is wrapped in try/except so transient failures never crash the run.
"""

import os
import warnings
from typing import List, Type

from pydantic import BaseModel, Field

# Suppress pydantic v1 compat warning from crewai_tools internals
warnings.filterwarnings(
    "ignore",
    message="Support for class-based `config` is deprecated",
    category=DeprecationWarning,
)

import requests
from crewai.tools import BaseTool


# ---------------------------------------------------------------------------
# Step 3 fix: minimal, flat schema — no additionalProperties, no nesting.
# Groq rejects schemas with additionalProperties:false; keeping it simple
# also prevents CrewAI from bloating the tool description with the schema dump.
# ---------------------------------------------------------------------------

class _SearchInput(BaseModel):
    """Input for SafeSearch."""
    query: str = Field(description="The search query string, e.g. 'AI tools pricing 2026'")

    @classmethod
    def model_json_schema(cls, **kwargs):
        """Return schema without additionalProperties — Groq rejects that field."""
        schema = super().model_json_schema(**kwargs)
        schema.pop("additionalProperties", None)
        return schema


class SafeSearchTool(BaseTool):
    """Search the web. Use query='your search terms'. Example: query='AI tools 2026 pricing'"""

    name: str = "SafeSearch"
    # Short, unambiguous description — no schema dump injected.
    # CrewAI appends schema info automatically; keeping this brief prevents
    # the LLM from seeing a 300-char description that confuses tool-call generation.
    description: str = "Search the web. Input: query (string). Example: query='AI developer tools 2026'"
    args_schema: Type[BaseModel] = _SearchInput

    # Public counters — read by crew.py after the run
    search_count: int = 0
    skipped_sources: List[str] = []
    # PHASE 2 ADDITION — count of searches served from the local cache
    cache_hits: int = 0

    def _run(self, query: str, **kwargs) -> str:
        """Execute one web search, subject to the source cap. Never raises."""
        max_sources = int(os.getenv("MAX_SOURCES", "15"))
        api_key = os.getenv("SERPER_API_KEY")

        # ---- Runaway guard ------------------------------------------------
        if self.search_count >= max_sources:
            self.skipped_sources.append(query)
            return (
                f"SEARCH LIMIT REACHED ({max_sources} searches used). "
                "STOP calling this tool. Compile your findings now and write your final answer."
            )

        if not api_key:
            self.skipped_sources.append(query)
            return f"[SafeSearch] No SERPER_API_KEY configured. Skipping: '{query}'"

        # ---- PHASE 2: check cache before calling the external API ---------
        # Wrapped in try/except so a cache failure always falls through to
        # the real search — this must never block or break a run.
        try:
            from backend.storage.db import get_cached_search, save_cached_search
            cached_result = get_cached_search(query)
            if cached_result is not None:
                # Cache hit — do NOT count against MAX_SOURCES (no real call)
                self.cache_hits += 1
                return cached_result
        except Exception:
            pass  # cache error → fall through to live search

        # ---- Live call ----------------------------------------------------
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                json={"q": query},
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("organic", []):
                title   = item.get("title", "")
                link    = item.get("link", "")
                snippet = item.get("snippet", "")
                # Truncate snippet to 250 chars to keep Researcher context
                # well under Groq's 6000 TPM limit (fix for RateLimitError).
                # Shape of each result entry is unchanged — just shorter text.
                if len(snippet) > 250:
                    snippet = snippet[:250] + "..."
                results.append(f"- {title}\n  {link}\n  {snippet}")

            self.search_count += 1
            result_text = "\n\n".join(results) if results else f"[SafeSearch] No results for: '{query}'"

            # PHASE 2: save to cache on success (silently, never blocks)
            try:
                from backend.storage.db import save_cached_search
                save_cached_search(query, result_text, source_name="serper")
            except Exception:
                pass

            return result_text

        except Exception as exc:
            self.skipped_sources.append(query)
            if "403" in str(exc):
                return (
                    "[SafeSearch] Serper API key invalid (403). "
                    "Set SERPER_API_KEY in .env. Skipping this query."
                )
            return f"[SafeSearch] Source unreachable, skipped. Query: '{query}' — {exc}"
