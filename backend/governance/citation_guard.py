"""
Citation and verification governance — enforced programmatically, not just prompted.

WHY THIS GUARDRAIL EXISTS:
LLM-based agents can be instructed to only produce cited claims, but they will
occasionally hallucinate an uncited assertion or slip in a sensational claim
backed by a single dubious source.  Rather than trusting the prompt alone, we
enforce two rules at the Python level after the agent writes its output:

1. **enforce_citations** — any Claim whose `is_properly_sourced` is False is
   *removed* from the briefing entirely.  Uncited claims never reach the user.

2. **flag_unverified_assertions** — certain high‑risk keywords (bankrupt,
   lawsuit, fraud, …) trigger extra scrutiny: if the claim only has a single
   citation from a non‑major outlet, we prefix it with "Unverified: " rather
   than dropping it.  This lets the user see the information while being warned
   of its low confidence.
"""

from typing import List, Tuple

from backend.models.schemas import Claim, Section


# ---------------------------------------------------------------------------
# 1.  Drop any claim that has zero citations
# ---------------------------------------------------------------------------

def enforce_citations(
    sections: List[Section],
) -> Tuple[List[Section], List[str]]:
    """Remove every Claim that has no citations.

    Returns:
        cleaned_sections — same structure, but uncited claims are gone.
        flags            — human‑readable notes describing what was dropped.
    """
    flags: List[str] = []
    cleaned: List[Section] = []

    for section in sections:
        surviving: List[Claim] = []
        for claim in section.claims:
            if not claim.is_properly_sourced:
                snippet = claim.text[:60] + ("..." if len(claim.text) > 60 else "")
                flags.append(f"Dropped uncited claim: '{snippet}'")
                # Claim is dropped — does NOT appear in surviving list.
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
    suspicious_keywords: List[str] | None = None,
) -> Tuple[List[Section], List[str]]:
    """Prefix any claim that matches high‑risk keywords and has weak sourcing.

    "Weak sourcing" here means exactly one citation whose source_name is NOT
    in a small allowlist of known major outlets.  Such claims are prefixed
    with "Unverified: " and marked verified=False instead of being dropped.

    Returns:
        cleaned_sections — same sections, possibly with modified claims.
        flags            — human‑readable notes describing what was hedged.
    """
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
                flags.append(
                    f"Hedged unverified claim: '{snippet}' "
                    f"— single source: {claim.citations[0].source_name}"
                )
            else:
                # Either multiple sources or a trustworthy source — leave as is.
                updated_claims.append(claim)

        modified.append(Section(title=section.title, claims=updated_claims))

    return modified, flags