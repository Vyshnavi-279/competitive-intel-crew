"""
backend/main.py — FastAPI application entry point.

Endpoints
---------
POST  /api/run                      Run a new competitive-intelligence briefing.
GET   /api/runs                     List recent run summaries (dashboard history).
GET   /api/runs/{run_id}            Retrieve the full briefing JSON for a run.
POST  /api/runs/{run_id}/publish    Flip status from "pending_review" → "published".
POST  /api/runs/{run_id}/reject     Flip status from "pending_review" → "rejected"
                                    with an optional free-text reason.
GET   /api/health                   Liveness probe.

Start the server
----------------
    uvicorn backend.main:app --reload --port 8000

Requires a populated .env file (see backend/config.py for required keys).
CORS is enabled for http://localhost:3000 (the React dev server).

Scheduler
---------
The APScheduler BackgroundScheduler is started during the FastAPI lifespan
startup event and gracefully shut down on shutdown.  It does not block the
API event loop — all crew work runs in APScheduler's thread-pool executor.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Config is imported first so a missing env var aborts startup immediately.
from backend.config import settings  # noqa: F401  (validates on import)
from backend.crew import run_briefing
from backend.scheduler import create_scheduler
from backend.storage.db import (
    get_run,
    init_db,
    list_runs,
    log_event,
    save_run,
    update_run_status,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — startup: init DB + start scheduler; shutdown: stop scheduler
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown.

    Startup order:
      1. init_db()      — ensure the SQLite file and tables exist.
      2. scheduler.start() — launch the background weekly-briefing job.

    Shutdown order:
      1. scheduler.shutdown(wait=False) — stop APScheduler without blocking
         the shutdown path.  In-flight crew runs are allowed to finish (they
         run in daemon threads) but we don't wait for them.
    """
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Initialising database …")
    init_db()
    logger.info("Database ready.")

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started.")

    # Stash on app.state so tests or other code can inspect it if needed.
    app.state.scheduler = scheduler

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down scheduler …")
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Competitive Intel Crew API",
    description=(
        "REST interface for triggering competitive-intelligence crew runs, "
        "retrieving briefings, and managing the human-review workflow."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the React dev server to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    """Body for POST /api/run."""
    topic: str


class PublishResponse(BaseModel):
    """Body returned by POST /api/runs/{run_id}/publish."""
    run_id: str
    status: str
    message: str


class RejectRequest(BaseModel):
    """Optional body for POST /api/runs/{run_id}/reject."""
    reason: Optional[str] = None


class RejectResponse(BaseModel):
    """Body returned by POST /api/runs/{run_id}/reject."""
    run_id: str
    status: str
    reason: Optional[str]
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health", tags=["meta"])
async def health() -> Dict[str, str]:
    """Liveness probe — returns 200 OK with ``{"status": "ok"}``."""
    return {"status": "ok"}


@app.get("/api/status", tags=["meta"])
async def api_status() -> Dict[str, Any]:
    """Return Groq account/model status.

    Calls the Groq models endpoint to confirm the API key is valid and the
    configured model is available.  Returns a structured summary suitable
    for display in the frontend header.  If the upstream call fails for any
    reason, status is set to 'unknown' so the app stays usable.
    """
    model_name: str = settings.model_name

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            )
            if resp.status_code == 401:
                return {
                    "model": model_name,
                    "is_free_tier": True,
                    "daily_limit": 0,
                    "status": "error",
                    "message": "Invalid Groq API key. Check GROQ_API_KEY in .env",
                }
            resp.raise_for_status()
            data = resp.json()

        # Confirm the configured model exists in the returned list
        available_ids = {m.get("id", "") for m in data.get("data", [])}
        # Model name in .env is "groq/llama-3.3-70b-versatile"; strip provider prefix
        bare_model = model_name.replace("groq/", "")
        model_available = bare_model in available_ids

        if not model_available:
            return {
                "model": model_name,
                "is_free_tier": True,
                "daily_limit": 0,
                "status": "error",
                "message": (
                    f"Model '{bare_model}' not found on Groq. "
                    f"Check MODEL_NAME in .env. Available: {sorted(available_ids)}"
                ),
            }

        return {
            "model": model_name,
            "is_free_tier": True,
            "daily_limit": 0,
            "status": "ok",
            "message": "Groq API key valid and model available.",
        }

    except Exception:
        return {
            "model": model_name,
            "is_free_tier": True,
            "daily_limit": 0,
            "status": "unknown",
            "message": "Could not reach Groq API. Check your connection.",
        }


@app.post("/api/run", tags=["runs"])
async def create_run(body: RunRequest) -> Dict[str, Any]:
    """Kick off a new competitive-intelligence crew run.

    1. Calls ``run_briefing(topic, triggered_by="manual")``.
    2. Persists the resulting Briefing via ``save_run``.
    3. Writes audit-log entries ("run started", "run completed" / "run failed").
    4. Returns the full briefing as JSON.

    The crew's internal exception handling ensures ``run_briefing`` never
    raises — callers should check ``briefing.metadata.status`` for failures.
    After governance checks the status will be ``"pending_review"`` (not
    ``"completed"``) so a human must approve before ``"published"``.
    """
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(status_code=422, detail="topic must not be empty")

    logger.info("Manual run requested for topic: %s", topic)

    briefing = await run_briefing(topic, triggered_by="manual")
    run_id = briefing.metadata.run_id

    # Persist before logging (FK constraint in audit_log).
    save_run(briefing)

    log_event(run_id, "run started")
    if briefing.metadata.status == "failed":
        log_event(run_id, "run failed")
    else:
        log_event(run_id, "awaiting review")

    logger.info(
        "Run %s finished: status=%s, duration=%.1fs",
        run_id,
        briefing.metadata.status,
        briefing.metadata.duration_seconds or 0,
    )

    return briefing.to_dict()


@app.get("/api/runs", tags=["runs"])
async def get_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Return lightweight summaries of the most recent runs.

    Each item includes: run_id, topic, started_at, status, sources_used,
    sources_skipped_count, and triggered_by.

    Query parameters
    ----------------
    limit : int, default 20
        Maximum number of rows to return (newest first, max 200).
    """
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=422, detail="limit must be between 1 and 200"
        )
    return list_runs(limit=limit)


@app.get("/api/runs/{run_id}", tags=["runs"])
async def get_run_detail(run_id: str) -> Dict[str, Any]:
    """Return the full stored briefing JSON for *run_id*.

    Raises 404 if *run_id* is not found.
    """
    data = get_run(run_id)
    if data is None:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' not found."
        )
    return data


@app.post("/api/runs/{run_id}/publish", tags=["runs"])
async def publish_run(run_id: str) -> PublishResponse:
    """Approve a briefing and transition its status to ``"published"``.

    This is the *only* path by which a run reaches ``"published"`` — the
    crew never self-publishes.  The endpoint:

    1. Verifies the run exists.
    2. Guards that the current status is ``"pending_review"`` (prevents
       double-publishing and stops failed runs from being published).
    3. Updates the DB status column.
    4. Writes an audit-log entry ``"published by reviewer"``.

    Raises
    ------
    404 : run_id not found
    409 : current status is not ``"pending_review"``
    """
    data = get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    current_status = data.get("metadata", {}).get("status")
    if current_status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run '{run_id}' cannot be published: "
                f"status is '{current_status}', expected 'pending_review'."
            ),
        )

    if not update_run_status(run_id, "published"):
        raise HTTPException(status_code=500, detail="Status update failed.")

    log_event(run_id, "published by reviewer")
    logger.info("Run %s published.", run_id)

    return PublishResponse(
        run_id=run_id,
        status="published",
        message=f"Run '{run_id}' has been published successfully.",
    )


@app.post("/api/runs/{run_id}/reject", tags=["runs"])
async def reject_run(run_id: str, body: RejectRequest = RejectRequest()) -> RejectResponse:
    """Reject a briefing that is awaiting human review.

    Transitions the status from ``"pending_review"`` to ``"rejected"`` and
    records the reviewer's reason (if supplied) in the audit log.  A
    rejected run is preserved in the DB for traceability — it is never
    deleted.

    Request body (optional JSON):
        { "reason": "Insufficient sourcing on Section 2" }

    Raises
    ------
    404 : run_id not found
    409 : current status is not ``"pending_review"``
    """
    data = get_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    current_status = data.get("metadata", {}).get("status")
    if current_status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run '{run_id}' cannot be rejected: "
                f"status is '{current_status}', expected 'pending_review'."
            ),
        )

    if not update_run_status(run_id, "rejected"):
        raise HTTPException(status_code=500, detail="Status update failed.")

    reason = (body.reason or "").strip() or None
    audit_text = "rejected by reviewer"
    if reason:
        audit_text += f": {reason}"

    log_event(run_id, audit_text)
    logger.info("Run %s rejected. Reason: %s", run_id, reason or "(none)")

    return RejectResponse(
        run_id=run_id,
        status="rejected",
        reason=reason,
        message=f"Run '{run_id}' has been rejected.",
    )
