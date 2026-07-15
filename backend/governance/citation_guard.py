"""
Citation and verification governance — enforced programmatically, not just prompted.

WHY THIS GUARDRAIL EXISTS:
LLM-based agents can be instructed to only produce cited claims, but they will
occasionally hallucinate an uncited assertion or slip in a sensational claim
backed by a single dubious source.  Rather than trusting the prompt alone, we
enforce two rules at the Python level after the agent writes its output:

1. **enforce_citations** — any Claim whose `is_properly_sourced` is False is
   *removed* from the briefing entirely.  Uncited claims never reach the user
   (FR-4: "Claims without a citation must never reach the final output").

2. **flag_unverified_assertions** — certain high‑risk keywords (bankrupt,
   lawsuit, fraud, …) trigger extra scrutiny: if the claim only has a single
   citation from a non‑major outlet, we prefix it with "Unverified: " rather
   than dropping it.  This lets the user see the information while being warned
   of its low confidence.

Both functions accept an optional ``run_id`` argument so they can write audit-log
entries via ``log_event()``.  Pass the current run's ID when calling from
``run_briefing()``; omit (or pass None) in unit tests.
"""

from typing import List, Optional, Tuple

from backend.models.schemas import Claim, Section


# ---------------------------------------------------------------------------
# 1.  Drop any claim that has zero citations  (FR-4)
# ---------------------------------------------------------------------------

def enforce_citations(
    sections: List[Section],
    run_id: Optional[str] = None,
) -> Tuple[List[Section], List[str]]:
    """Drop every Claim that has no citations from the briefing.

    FR-4 specifies: "Claims without a citation must never reach the final
    output."  This function is the enforcement point — uncited claims are
    removed, never merely flagged.

    Parameters
    ----------
    sections:
        The list of Section objects produced by the Writer agent.
    run_id:
        If provided, each dropped claim is logged to the audit_log table
        via ``log_event(run_id, ...)``.  Pass None to skip DB logging
        (e.g. in unit tests).

    Returns
    -------
    cleaned_sections : List[Section]
        Same structure with uncited claims removed.
    flags : List[str]
        Human-readable notes describing which claims were dropped.
    """
    # Import here (not at module top) to avoid a circular-import cycle:
    # db.py imports schemas.py; schemas.py has no circular deps; but if
    # citation_guard.py (imported by crew.py) imported db.py at module level
    # and db.py imported crew.py, we'd have a cycle.  The lazy import below
    # is safe and only fires when run_id is actually passed.
    _log_event = None
    if run_id is not None:
        from backend.storage.db import log_event as _log_event  # type: ignore[assignment]

    flags: List[str] = []
    cleaned: List[Section] = []

    for section in sections:
        surviving: List[Claim] = []
        for claim in section.claims:
            if not claim.is_properly_sourced:
                snippet = claim.text[:60] + ("..." if len(claim.text) > 60 else "")
                flag_msg = f"[citation_guard] Dropped uncited claim in '{section.title}': '{snippet}'"
                flags.append(flag_msg)
                # Write to audit_log so the reviewer can see what was removed.
                if _log_event is not None:
                    try:
                        _log_event(run_id, flag_msg)
                    except Exception:
                        pass  # never let logging failure break the pipeline
                # Claim is NOT added to surviving — it is dropped (FR-4).
            else:
                surviving.append(claim)
        cleaned.append(Section(title=section.title, claims=surviving))

    return cleaned, flags


# ---------------------------------------------------------------------------
# 2.  Flag claims about high‑risk topics that are weakly sourced
# ---------------------------------------------------------------------------

# Outlets whose name alone signals "probably trustworthy" for the heuristic.
_TRUSTED_OUTLETS: set[str] = {
    "Reuters",
    "Bloomberg",
    "company press release",
    "SEC filing",
    "Associated Press",
    "Financial Times",
    "Wall Street Journal",
}


def flag_unverified_assertions(
    sections: List[Section],
    suspicious_keywords: Optional[List[str]] = None,
    run_id: Optional[str] = None,
) -> Tuple[List[Section], List[str]]:
    """Prefix any claim that matches high‑risk keywords and has weak sourcing.

    "Weak sourcing" here means exactly one citation whose source_name is NOT
    in a small allowlist of known major outlets.  Such claims are prefixed
    with "Unverified: " and marked verified=False instead of being dropped.

    Parameters
    ----------
    sections:
        Section list after ``enforce_citations`` has already run.
    suspicious_keywords:
        Extra keywords to watch for (defaults to bankrupt / lawsuit / fraud /
        shutting down / insolvent).
    run_id:
        If provided, each hedged claim is logged to the audit_log table.

    Returns
    -------
    modified_sections : List[Section]
        Same sections, possibly with "Unverified: " prefixes on weak claims.
    flags : List[str]
        Human-readable notes describing what was hedged.
    """
    _log_event = None
    if run_id is not None:
        from backend.storage.db import log_event as _log_event  # type: ignore[assignment]

    if suspicious_keywords is None:
        suspicious_keywords = [
            "bankrupt", "lawsuit", "fraud",
            "shutting down", "insolvent",
        ]

    flags: List[str] = []
    modified: List[Section] = []

    for section in sections:
        updated_claims: List[Claim] = []
        for claim in section.claims:
            # Only inspect claims that contain a suspicious keyword.
            if not any(kw.lower() in claim.text.lower() for kw in suspicious_keywords):
                updated_claims.append(claim)
                continue

            # Heuristic: if there is exactly one citation from an untrusted source …
            if len(claim.citations) == 1 and claim.citations[0].source_name not in _TRUSTED_OUTLETS:
                prefix = "Unverified: "
                new_text = claim.text if claim.text.startswith(prefix) else prefix + claim.text
                updated_claims.append(
                    Claim(
                        text=new_text,
                        citations=claim.citations,
                        verified=False,
                    )
                )
                snippet = claim.text[:60] + ("..." if len(claim.text) > 60 else "")
                flag_msg = (
                    f"[citation_guard] Hedged unverified claim in '{section.title}': "
                    f"'{snippet}' — single source: {claim.citations[0].source_name}"
                )
                flags.append(flag_msg)
                if _log_event is not None:
                    try:
                        _log_event(run_id, flag_msg)
                    except Exception:
                        pass
            else:
                # Either multiple sources or a trustworthy source — leave as is.
                updated_claims.append(claim)

        modified.append(Section(title=section.title, claims=updated_claims))

    return modified, flags
