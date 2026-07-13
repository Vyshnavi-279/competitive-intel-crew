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
from typing import List

from backend.models.schemas import Citation


# Regex that matches either form:
#   [Source Name](url)
#   [Source Name]
# The source name group (1) is non-empty, url group (3) is optional.
_CITATION_PATTERN = re.compile(r"\[([^\]]+)\](?:\(([^)]+)\))?")


def extract_citations(text: str) -> List[Citation]:
    """Parse citation markers out of *text* and return a list of Citation objects.

    Supports:
        [Source Name](url)   — preferred, with URL
        [Source Name]        — also recognised (url will be None)

    Each unique source_name+url pair is returned only once to avoid duplicates.
    """
    seen: set[tuple[str, str | None]] = set()
    result: List[Citation] = []

    for match in _CITATION_PATTERN.finditer(text):
        source_name = match.group(1).strip()
        url = match.group(2).strip() if match.group(2) else None

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