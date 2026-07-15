from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    """A single reference or source backing a claim."""

    source_name: str
    url: Optional[str] = None


class Claim(BaseModel):
    """A factual assertion (possibly disputed) with supporting citations."""

    text: str
    citations: List[Citation] = Field(default_factory=list)
    verified: bool = False

    @property
    def is_properly_sourced(self) -> bool:
        """Return True only when at least one citation has been attached."""
        return len(self.citations) > 0


class Section(BaseModel):
    """A named section of the briefing whose title is drawn from a controlled vocabulary."""

    title: str
    claims: List[Claim] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, v: str) -> str:
        allowed = {
            "Executive Summary",
            "Competitor Pricing & Product Moves",
            "Market Signals",
        }
        if v not in allowed:
            raise ValueError(
                f"title must be one of {allowed}, got {v!r}"
            )
        return v


class RunMetadata(BaseModel):
    """Audit / observability payload for a single competitive-intel run."""

    run_id: str
    topic: str
    started_at: datetime
    duration_seconds: Optional[float] = None
    sources_attempted: int = 0
    sources_used: int = 0
    sources_skipped: List[str] = Field(default_factory=list)
    total_steps: int = 0
    token_estimate: Optional[int] = None
    status: Literal[
        "running", "completed", "failed", "published", "pending_review", "rejected"
    ] = "running"
    # Who (or what) initiated this run.  "manual" = user-submitted via the
    # API; "scheduled" = fired by the weekly APScheduler job.  Stored in the
    # DB and surfaced in the UI so operators can distinguish automated reports
    # from ad-hoc analyst requests.
    triggered_by: Literal["manual", "scheduled"] = "manual"
    # KPI: % of claims in the final briefing that carry at least one citation.
    # Populated after the governance layer runs; 100.0 means citation_guard
    # has enforced that every surviving claim is cited (FR-4).
    cited_claims_pct: Optional[float] = None


class Briefing(BaseModel):
    """Top-level container that ties together run metadata, sections, and
    a summary of claims that could not be verified."""

    metadata: RunMetadata
    sections: List[Section] = Field(default_factory=list)
    unverified_flags: List[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON‑compatible dictionary, converting datetimes to ISO‑format strings."""
        return self.model_dump(mode="json")