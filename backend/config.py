"""
backend/config.py — environment configuration loader.

Loads a .env file (if present) via python-dotenv, then validates that every
required environment variable is set.  A missing required key raises a
RuntimeError at startup so the problem is caught immediately, rather than
surfacing later as a confusing KeyError inside a running request.

Usage
-----
    from backend.config import settings

    settings.groq_api_key     # str
    settings.serper_api_key   # str
    settings.model_name       # str
    settings.max_sources      # int
    settings.max_steps        # int

The module-level `settings` singleton is built on first import.  All other
modules should import from here rather than calling os.getenv directly, so
there is a single place to audit configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env — look for it at the project root (two levels up from this file)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent  # competitive-intel-crew/
load_dotenv(_PROJECT_ROOT / ".env", override=True)

# ---------------------------------------------------------------------------
# Required vs optional keys
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = (
    "SERPER_API_KEY",
)

_OPTIONAL_DEFAULTS = {
    "MODEL_NAME": "groq/llama-3.3-70b-versatile",
    "MAX_SOURCES": "15",
    "MAX_STEPS": "10",
    "MAX_TOKENS": "1500",
    # PHASE 5 ADDITION — multi-tenant auth pilot flag.
    # Default is "false" so the app behaves exactly as before unless
    # explicitly opted in.  This is a pilot placeholder — not production auth.
    "ENABLE_MULTI_TENANT_AUTH": "false",
}


def _validate() -> None:
    """Raise RuntimeError listing every missing required variable.

    Provider-agnostic key validation:
    - SERPER_API_KEY is always required.
    - At least one LLM API key must be present.  Accepted combinations:
        • GENERIC_LLM_API_KEY alone  — works for any provider (Gemini, etc.)
        • GROQ_API_KEY alone         — works for groq/* models
        • Both set                   — GENERIC_LLM_API_KEY takes priority for
                                       gemini/* models; GROQ_API_KEY for others
    This lets Render (and any deployment) set only GENERIC_LLM_API_KEY without
    also needing GROQ_API_KEY when switching to a non-Groq provider.
    """
    missing = [k for k in _REQUIRED_KEYS if not os.getenv(k)]

    has_generic = bool(os.getenv("GENERIC_LLM_API_KEY"))
    has_groq    = bool(os.getenv("GROQ_API_KEY"))
    if not has_generic and not has_groq:
        missing.append("GROQ_API_KEY or GENERIC_LLM_API_KEY")

    if missing:
        raise RuntimeError(
            "Missing required environment variables — set them in your .env "
            "file or export them before starting the server:\n"
            + "\n".join(f"  • {k}" for k in missing)
        )


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """Typed, immutable snapshot of the current environment configuration."""

    serper_api_key: str
    model_name: str
    max_sources: int
    max_steps: int
    max_tokens: int
    # groq_api_key is None when MODEL_NAME starts with "gemini/".
    groq_api_key: str = ""
    # generic_llm_api_key is None when MODEL_NAME does not start with "gemini/".
    generic_llm_api_key: str = ""
    # PHASE 5 ADDITION — multi-tenant auth pilot flag (off by default).
    # When True a minimal username-only login modal is shown in the frontend.
    # This is a pilot placeholder; set to False for all normal use.
    enable_multi_tenant_auth: bool = False

    @property
    def llm_api_key(self) -> str:
        """Return the correct API key for the configured model provider.

        Priority:
        - gemini/* models  → GENERIC_LLM_API_KEY (required)
        - all other models → GROQ_API_KEY if set, else GENERIC_LLM_API_KEY
          (allows deployments that only set GENERIC_LLM_API_KEY to work with
          any provider without also needing GROQ_API_KEY)
        """
        if self.model_name.startswith("gemini/"):
            return self.generic_llm_api_key
        return self.groq_api_key or self.generic_llm_api_key


def _load_settings() -> Settings:
    """Validate env vars and return a populated Settings instance."""
    _validate()
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        generic_llm_api_key=os.getenv("GENERIC_LLM_API_KEY", ""),
        serper_api_key=os.environ["SERPER_API_KEY"],
        model_name=os.getenv("MODEL_NAME", _OPTIONAL_DEFAULTS["MODEL_NAME"]),
        max_sources=int(os.getenv("MAX_SOURCES", _OPTIONAL_DEFAULTS["MAX_SOURCES"])),
        max_steps=int(os.getenv("MAX_STEPS", _OPTIONAL_DEFAULTS["MAX_STEPS"])),
        max_tokens=int(os.getenv("MAX_TOKENS", _OPTIONAL_DEFAULTS["MAX_TOKENS"])),
        # PHASE 5: parse the flag — any truthy string ("true", "1", "yes") enables it
        enable_multi_tenant_auth=(
            os.getenv(
                "ENABLE_MULTI_TENANT_AUTH",
                _OPTIONAL_DEFAULTS["ENABLE_MULTI_TENANT_AUTH"]
            ).lower() in ("true", "1", "yes")
        ),
    )


# ---------------------------------------------------------------------------
# Module-level singleton — validated once on import
# ---------------------------------------------------------------------------

settings: Settings = _load_settings()