"""
backend/config.py — environment configuration loader.

Loads a .env file (if present) via python-dotenv, then validates that every
required environment variable is set.  A missing required key raises a
RuntimeError at startup so the problem is caught immediately, rather than
surfacing later as a confusing KeyError inside a running request.

IMPORTANT — .env always wins
------------------------------
We call load_dotenv with override=True AND then explicitly write every key
back into os.environ.  This ensures that vars set on the Render dashboard or
in the macOS launchctl environment can NEVER silently override the values in
.env.  The .env file is the single source of truth for all deployments.

Usage
-----
    from backend.config import settings

    settings.llm_api_key      # str  — the API key for the configured provider
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
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# ---------------------------------------------------------------------------
# Load .env — look for it at the project root (two levels up from this file)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent  # competitive-intel-crew/
_ENV_PATH = _PROJECT_ROOT / ".env"

# Step 1: load .env into os.environ (override=True overrides previously-loaded
# dotenv values, but NOT pre-existing shell/system env vars on all platforms).
load_dotenv(_ENV_PATH, override=True)

# Step 2: read the raw .env file values directly and forcibly write them into
# os.environ so they win over Render dashboard vars, launchctl vars, etc.
if _ENV_PATH.exists():
    _raw = dotenv_values(_ENV_PATH)
    for _k, _v in _raw.items():
        if _v is not None:
            os.environ[_k] = _v

# ---------------------------------------------------------------------------
# Provider detection helpers
# ---------------------------------------------------------------------------

def _detect_provider(model_name: str) -> str:
    """Return the provider slug for a given model string."""
    m = model_name.lower()
    if m.startswith("groq/") or m.startswith("groq"):
        return "groq"
    if m.startswith("openrouter/") or m.startswith("openrouter"):
        return "openrouter"
    if m.startswith("gemini/") or "google" in m:
        return "gemini"
    if m.startswith("openai/") or m.startswith("gpt-"):
        return "openai"
    if m.startswith("anthropic/") or "claude" in m:
        return "anthropic"
    return "groq"  # safe default — project was built for Groq


def _resolve_api_key(provider: str) -> str:
    """Return the correct API key env var for the provider, with fallbacks."""
    candidates: list[str] = {
        "groq":       ["GROQ_API_KEY"],
        "openrouter": ["OPENROUTER_API_KEY", "GENERIC_LLM_API_KEY", "GROQ_API_KEY"],
        "gemini":     ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GENERIC_LLM_API_KEY"],
        "openai":     ["OPENAI_API_KEY", "GENERIC_LLM_API_KEY"],
        "anthropic":  ["ANTHROPIC_API_KEY", "GENERIC_LLM_API_KEY"],
    }.get(provider, ["GROQ_API_KEY"])

    for var in candidates:
        val = os.getenv(var, "").strip()
        if val:
            return val
    return ""


# ---------------------------------------------------------------------------
# Required vs optional keys
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = (
    "SERPER_API_KEY",
)

_OPTIONAL_DEFAULTS = {
    "MODEL_NAME": "groq/llama-3.3-70b-versatile",
    "MAX_SOURCES": "3",
    "MAX_STEPS":   "10",
    "MAX_TOKENS":  "1000",
    "ENABLE_MULTI_TENANT_AUTH": "false",
}


def _validate(provider: str, api_key: str) -> None:
    """Raise RuntimeError listing every missing required variable."""
    missing = [k for k in _REQUIRED_KEYS if not os.getenv(k)]
    if not api_key:
        missing.append(f"API key for provider '{provider}' (set GROQ_API_KEY or matching key)")
    if missing:
        raise RuntimeError(
            "Missing required environment variables — set them in your .env "
            "file or in the Render dashboard:\n"
            + "\n".join(f"  • {k}" for k in missing)
        )


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """Typed, immutable snapshot of the current environment configuration."""

    # The API key appropriate for the configured provider
    llm_api_key: str
    # Keep groq_api_key as an alias so existing code that imports it doesn't break
    groq_api_key: str
    serper_api_key: str
    model_name: str
    provider: str
    max_sources: int
    max_steps: int
    max_tokens: int
    enable_multi_tenant_auth: bool = False


def _load_settings() -> Settings:
    """Validate env vars and return a populated Settings instance."""
    model_name = os.getenv("MODEL_NAME", _OPTIONAL_DEFAULTS["MODEL_NAME"]).strip()
    provider   = _detect_provider(model_name)
    api_key    = _resolve_api_key(provider)

    _validate(provider, api_key)

    return Settings(
        llm_api_key   = api_key,
        groq_api_key  = api_key,   # backward-compat alias
        serper_api_key= os.environ["SERPER_API_KEY"],
        model_name    = model_name,
        provider      = provider,
        max_sources   = int(os.getenv("MAX_SOURCES", _OPTIONAL_DEFAULTS["MAX_SOURCES"])),
        max_steps     = int(os.getenv("MAX_STEPS",   _OPTIONAL_DEFAULTS["MAX_STEPS"])),
        max_tokens    = int(os.getenv("MAX_TOKENS",  _OPTIONAL_DEFAULTS["MAX_TOKENS"])),
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
