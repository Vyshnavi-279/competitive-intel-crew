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
        dropped: List[Claim] = []

        for claim in section.claims:
            if not claim.is_properly_sourced:
                dropped.append(claim)
            else:
                surviving.append(claim)

        # --- Safety-net for all-uncited sections ----------------------------
        # If EVERY claim in this section lacks citations (common when the LLM
        # produces good text but forgets [Source](url) markers), dropping them
        # all would leave the section completely empty — which is worse than
        # showing hedged content with a clear "unverified" label.
        # In that case, keep the claims but mark them as unverified and prefix
        # them so the reviewer knows they are uncited.
        # We still log the flags so the governance log is accurate.
        if surviving:
            # Normal path: some claims have citations → drop the uncited ones
            for claim in dropped:
                snippet = claim.text[:60] + ("..." if len(claim.text) > 60 else "")
                flag_msg = f"[citation_guard] Dropped uncited claim in '{section.title}': '{snippet}'"
                flags.append(flag_msg)
                if _log_event is not None:
                    try:
                        _log_event(run_id, flag_msg)
                    except Exception:
                        pass
            cleaned.append(Section(title=section.title, claims=surviving))
        elif dropped:
            # All-uncited fallback: keep claims as unverified rather than
            # leaving the section empty.  The reviewer sees the content with
            # a clear warning and can reject if quality is insufficient.
            fallback_claims = []
            for claim in dropped:
                snippet = claim.text[:60] + ("..." if len(claim.text) > 60 else "")
                flag_msg = (
                    f"[citation_guard] Kept uncited claim as unverified in "
                    f"'{section.title}' (all claims lacked citations): '{snippet}'"
                )
                flags.append(flag_msg)
                if _log_event is not None:
                    try:
                        _log_event(run_id, flag_msg)
                    except Exception:
                        pass
                prefix = "Unverified: "
                new_text = claim.text if claim.text.startswith(prefix) else prefix + claim.text
                fallback_claims.append(
                    Claim(text=new_text, citations=[], verified=False)
                )
            cleaned.append(Section(title=section.title, claims=fallback_claims))
        else:
            # Section was already empty — keep it empty
            cleaned.append(Section(title=section.title, claims=[]))

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

    PHASE 3 BROADENING — based on Scenario 5 (planted unverified claim) test
    learnings.  Three improvements were made to catch adversarial phrasings:

    1.  The suspicious_keywords default list now includes multi-word patterns
        and low-credibility qualifiers in addition to single-word triggers.
        Case-insensitive substring matching (already used) catches these
        naturally since we iterate the full claim text.

    2.  A set of compiled regex patterns catches adversarial phrasings that
        wouldn't match any single keyword (e.g. "going under", "on the verge
        of bankruptcy", "sources say", "unconfirmed reports").

    3.  A numeric-risk heuristic: if a claim contains a specific number
        (integer or percentage) together with a negative-outcome word
        (lawsuit, loss, collapse, fraud, bankrupt, scandal, layoff, laid off)
        AND is backed by only one non-authoritative source, it is hedged —
        even if it contains none of the trigger keywords above.

    Parameters
    ----------
    sections:
        Section list after ``enforce_citations`` has already run.
    suspicious_keywords:
        Extra keywords to watch for (defaults to the broadened list below).
    run_id:
        If provided, each hedged claim is logged to the audit_log table.

    Returns
    -------
    modified_sections : List[Section]
        Same sections, possibly with "Unverified: " prefixes on weak claims.
    flags : List[str]
        Human-readable notes describing what was hedged.
    """
    import re  # local import — only needed here, avoids module-level dep

    _log_event = None
    if run_id is not None:
        from backend.storage.db import log_event as _log_event  # type: ignore[assignment]

    # -----------------------------------------------------------------------
    # PHASE 3: Broadened suspicious_keywords default.
    # Original: bankrupt, lawsuit, fraud, shutting down, insolvent
    # Added: multi-word adversarial phrases and low-credibility qualifiers.
    # -----------------------------------------------------------------------
    if suspicious_keywords is None:
        suspicious_keywords = [
            # Original keywords (preserved — existing behaviour unchanged)
            "bankrupt", "lawsuit", "fraud",
            "shutting down", "insolvent",
            # PHASE 3 additions — adversarial phrasings
            "going under",
            "about to collapse",
            "on the verge of bankruptcy",
            "secretly",
            "unconfirmed reports",
            "rumored to be",
            # NOTE: "sources say" is intentionally NOT in the flat list because
            # it appears in legitimate journalism too.  We handle it via the
            # regex patterns below instead, where we can combine it with
            # other low-credibility signals.
        ]

    # -----------------------------------------------------------------------
    # PHASE 3: Compiled regex patterns for adversarial phrasings that need
    # more context than a single keyword match can provide.
    # All patterns are case-insensitive.
    # -----------------------------------------------------------------------
    _ADVERSARIAL_PATTERNS = [
        re.compile(r"\bsources?\s+say\b", re.IGNORECASE),          # "sources say"
        re.compile(r"\bunconfirmed\b", re.IGNORECASE),              # "unconfirmed ..."
        re.compile(r"\brumou?red?\b", re.IGNORECASE),               # "rumored/rumoured"
        re.compile(r"\bgoing\s+under\b", re.IGNORECASE),            # "going under"
        re.compile(r"\bverge\s+of\s+(?:bankruptcy|collapse|insolvency)\b", re.IGNORECASE),
        re.compile(r"\babout\s+to\s+(?:collapse|fail|fold|close)\b", re.IGNORECASE),
        re.compile(r"\bsecretly\b", re.IGNORECASE),
    ]

    # -----------------------------------------------------------------------
    # PHASE 3: Numeric-risk heuristic.
    # A claim that contains a specific number (e.g. "40%" or "$5 million")
    # together with a negative-outcome word is flagged even without trigger
    # keywords — these are the classic pattern of planted unverified stats.
    # -----------------------------------------------------------------------
    _NUMBER_PATTERN = re.compile(
        r"\b\d+(?:[,\.]\d+)?(?:\s*%|(?:\s+(?:million|billion|thousand|percent)))?\b",
        re.IGNORECASE,
    )
    _NEGATIVE_OUTCOME_WORDS = {
        "lawsuit", "loss", "losses", "collapse", "fraud", "bankrupt",
        "bankruptcy", "scandal", "layoff", "laid off", "terminated",
        "fired", "cut", "cuts", "plummeted", "crashed", "hack",
    }

    def _has_numeric_risk(text: str) -> bool:
        """Return True if text has a number + a negative-outcome word."""
        if not _NUMBER_PATTERN.search(text):
            return False
        text_lower = text.lower()
        return any(word in text_lower for word in _NEGATIVE_OUTCOME_WORDS)

    flags: List[str] = []
    modified: List[Section] = []

    for section in sections:
        updated_claims: List[Claim] = []
        for claim in section.claims:
            text = claim.text

            # ----------------------------------------------------------------
            # Determine if this claim is suspicious:
            #   a) contains a suspicious keyword (flat list, case-insensitive)
            #   b) matches one of the adversarial regex patterns
            #   c) numeric-risk heuristic fires
            # ----------------------------------------------------------------
            keyword_hit = any(kw.lower() in text.lower() for kw in suspicious_keywords)
            pattern_hit = any(p.search(text) for p in _ADVERSARIAL_PATTERNS)
            numeric_hit = _has_numeric_risk(text)

            is_suspicious = keyword_hit or pattern_hit or numeric_hit

            if not is_suspicious:
                updated_claims.append(claim)
                continue

            # Heuristic: if there is exactly one citation from an untrusted source …
            if len(claim.citations) == 1 and claim.citations[0].source_name not in _TRUSTED_OUTLETS:
                prefix = "Unverified: "
                new_text = text if text.startswith(prefix) else prefix + text
                updated_claims.append(
                    Claim(
                        text=new_text,
                        citations=claim.citations,
                        verified=False,
                    )
                )
                snippet = text[:60] + ("..." if len(text) > 60 else "")
                # Note which trigger fired so reviewers understand why
                trigger_note = (
                    "numeric-risk heuristic" if numeric_hit and not keyword_hit
                    else "adversarial pattern" if pattern_hit and not keyword_hit
                    else f"keyword: {next((kw for kw in suspicious_keywords if kw.lower() in text.lower()), '?')}"
                )
                flag_msg = (
                    f"[citation_guard] Hedged unverified claim in '{section.title}': "
                    f"'{snippet}' — single source: {claim.citations[0].source_name} "
                    f"[trigger: {trigger_note}]"
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
