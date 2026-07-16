"""
Citation-parsing helpers for raw agent output.

Agents often write inline citation markers like:
    "Acme raised prices by 10% [Reuters](https://reuters.com/...)"
or
    "Acme raised prices by 10% [Reuters]"

These functions extract structured Citation objects from such text and also
produce a clean version with the markup removed.
"""

import re
from typing import List, Optional
from urllib.parse import urlparse

from backend.models.schemas import Citation


# Regex that matches either form:
#   [Source Name](url)
#   [Source Name]
# The source name group (1) is non-empty, url group (2) is optional.
_CITATION_PATTERN = re.compile(r"\[([^\]]+)\](?:\(([^)]+)\))?")


def _is_valid_url(url: Optional[str]) -> bool:
    """Return True only for real http/https URLs with a host.

    Filters out:
    - Placeholder text like 'url', 'URL', 'link', 'source'
    - Bare filenames or paths without a scheme
    - Fragments (#...) only
    - Single-word non-URLs
    """
    if not url:
        return False
    url = url.strip()
    if not url:
        return False

    # Reject obviously fake placeholder text (case-insensitive)
    _PLACEHOLDERS = {
        "url", "link", "source", "here", "example.com",
        "example.org", "www.example.com", "http://example.com",
        "https://example.com", "website", "href", "#",
    }
    if url.lower() in _PLACEHOLDERS:
        return False

    # Must start with http:// or https://
    if not url.lower().startswith(("http://", "https://")):
        return False

    try:
        parsed = urlparse(url)
        # Must have a non-empty netloc (hostname) with at least one dot
        if not parsed.netloc or "." not in parsed.netloc:
            return False
        # Netloc must not be a placeholder
        if parsed.netloc.lower() in {"example.com", "example.org", "localhost"}:
            return False
        return True
    except Exception:
        return False


def extract_citations(text: str) -> List[Citation]:
    """Parse citation markers out of *text* and return a list of Citation objects.

    Supports:
        [Source Name](url)   — preferred, with URL
        [Source Name]        — also recognised (url will be None)

    Each unique source_name+url pair is returned only once to avoid duplicates.
    Only real, valid http/https URLs are kept — placeholder text is discarded.
    """
    seen: set[tuple[str, str | None]] = set()
    result: List[Citation] = []

    for match in _CITATION_PATTERN.finditer(text):
        source_name = match.group(1).strip()
        raw_url = match.group(2).strip() if match.group(2) else None

        # Validate the URL — drop placeholders and malformed values
        url: Optional[str] = raw_url if _is_valid_url(raw_url) else None

        # Skip citations where source_name looks like part of markdown syntax
        # e.g. [!NOTE] or empty brackets
        if not source_name or source_name.startswith("!"):
            continue

        key = (source_name, url)
        if key not in seen:
            seen.add(key)
            result.append(Citation(source_name=source_name, url=url))

    return result


def strip_citation_markers(text: str) -> str:
    """Remove all ``[Source Name](url)`` and ``[Source Name]`` markers.

    Returns the text with citation markup stripped out, leaving only the
    natural-language content — useful for clean display or for passing to
    an LLM that should not see the raw markup.
    """
    return _CITATION_PATTERN.sub("", text).strip()