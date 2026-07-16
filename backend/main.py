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
GET   /                             Root — basic service info (useful for host health checks).

Start the server
----------------
    uvicorn backend.main:app --reload --port 8000

Requires a populated .env file (see backend/config.py for required keys).

CORS
----
Allowed origins are read from the ALLOWED_ORIGINS env var (comma-separated),
in addition to localhost:3000 for local dev. Set ALLOWED_ORIGINS on your
backend host (Render, Railway, etc.) to your deployed frontend URL(s), e.g.:

    ALLOWED_ORIGINS=https://competitive-intel-crew.netlify.app,https://your-app.vercel.app

If ALLOWED_ORIGINS is not set, only localhost:3000 is allowed — deployed
frontends will get CORS errors until this is configured.

Scheduler
---------
The APScheduler BackgroundScheduler is started during the FastAPI lifespan
startup event and gracefully shut down on shutdown.  It does not block the
API event loop — all crew work runs in APScheduler's thread-pool executor.
"""

from __future__ import annotations

import logging
import os
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
    get_kpis,
    init_db,
    list_runs,
    log_event,
    save_run,
    update_run_status,
    delete_run,
    delete_failed_runs,
    get_stage_log,          # PHASE 1 ADDITION
    get_usage_analytics,    # PHASE 4 ADDITION
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

# CORS — allow local dev plus any deployed frontend URL(s) from ALLOWED_ORIGINS.
_extra_origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", *_extra_origins],
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
    # PHASE 4 ADDITION — who submitted this run.  Defaults to "default_user"
    # so existing callers that don't send this field continue to work exactly
    # as before.  No validation beyond being a non-empty string.
    submitted_by: str = "default_user"


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


@app.get("/", tags=["meta"])
async def root() -> Dict[str, str]:
    """Basic service info. Useful for host-level health checks that hit '/'."""
    return {"status": "ok", "service": "Competitive Intel Crew API"}


@app.get("/api/health", tags=["meta"])
async def health() -> Dict[str, str]:
    """Liveness probe — returns 200 OK with ``{"status": "ok"}``."""
    return {"status": "ok"}


# PHASE 5 ADDITION — config endpoint for the multi-tenant auth pilot.
# Read-only; exposes only the flags the frontend needs.
# NOTE: This is a pilot placeholder — not production auth/config management.
@app.get("/api/config", tags=["meta"])
async def get_config() -> Dict[str, Any]:
    """Return frontend-safe configuration flags.

    Currently exposes only one flag:
        multi_tenant_enabled: bool — when True the frontend shows the
        username-only login modal (PHASE 5 pilot).  Defaults to False so
        all existing behaviour is unchanged until explicitly enabled via
        the ENABLE_MULTI_TENANT_AUTH env var.

    Read-only and side-effect free.
    """
    return {
        "multi_tenant_enabled": settings.enable_multi_tenant_auth,
    }


@app.delete("/api/runs/failed", tags=["runs"])
async def delete_all_failed() -> Dict[str, Any]:
    """Delete all runs with status='failed' in one shot."""
    try:
        count = delete_failed_runs()
        return {"deleted": count, "message": f"Deleted {count} failed run(s)."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/runs/{run_id}", tags=["runs"])
async def delete_run_endpoint(run_id: str) -> Dict[str, Any]:
    """Delete a single run by ID (any status)."""
    try:
        if not delete_run(run_id):
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
        return {"deleted": run_id, "message": "Run deleted."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/kpis", tags=["meta"])
async def kpis() -> Dict[str, Any]:
    """Return the 5 business KPIs computed from all stored runs."""
    try:
        return get_kpis()
    except Exception as exc:
        logger.exception("Failed to compute KPIs")
        raise HTTPException(status_code=500, detail=f"KPI computation failed: {exc}") from exc


# PHASE 4 ADDITION — per-analyst usage + turnaround analytics
@app.get("/api/analytics/usage", tags=["analytics"])
async def analytics_usage() -> Dict[str, Any]:
    """Return per-analyst run counts, average durations, and a 30-day daily trend.

    Response shape:
        {
          "by_user": [
              {"submitted_by": str, "run_count": int, "avg_duration_seconds": float}
          ],
          "daily_trend": [
              {"date": "YYYY-MM-DD", "run_count": int}
          ]
        }

    Read-only and side-effect free.  Returns empty arrays if there are no
    runs yet, never raises a 500.
    """
    try:
        return get_usage_analytics()
    except Exception as exc:
        logger.exception("Failed to compute usage analytics")
        raise HTTPException(status_code=500, detail=f"Analytics query failed: {exc}") from exc


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
        # Model name in .env is "groq/llama-3.1-8b-instant"; strip provider prefix
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
    try:
        topic = body.topic.strip()
        if not topic:
            raise HTTPException(status_code=422, detail="topic must not be empty")

        logger.info("Manual run requested for topic: %s", topic)

        briefing = await run_briefing(topic, triggered_by="manual")
        run_id = briefing.metadata.run_id

        # PHASE 4: stamp who submitted this run onto the metadata so it's
        # persisted in the DB and available for analytics.
        try:
            submitted_by = (body.submitted_by or "default_user").strip() or "default_user"
            briefing.metadata.submitted_by = submitted_by
        except Exception:
            pass  # never break existing flow for new fields

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

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in create_run")
        raise HTTPException(status_code=500, detail=f"Internal server error: {exc}") from exc


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
    try:
        if limit < 1 or limit > 200:
            raise HTTPException(
                status_code=422, detail="limit must be between 1 and 200"
            )
        return list_runs(limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to list runs")
        raise HTTPException(status_code=500, detail=f"Failed to list runs: {exc}") from exc


@app.get("/api/runs/{run_id}", tags=["runs"])
async def get_run_detail(run_id: str) -> Dict[str, Any]:
    """Return the full stored briefing JSON for *run_id*.

    Raises 404 if *run_id* is not found.
    """
    try:
        data = get_run(run_id)
        if data is None:
            raise HTTPException(
                status_code=404, detail=f"Run '{run_id}' not found."
            )
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to retrieve run %s", run_id)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve run: {exc}") from exc


# PHASE 1 ADDITION — stage flow endpoint
@app.get("/api/runs/{run_id}/stages", tags=["runs"])
async def get_run_stages(run_id: str) -> List[Dict[str, Any]]:
    """Return the ordered stage_log rows for a run.

    Always returns all 5 canonical stages, merging:
      1. In-memory registry (most up-to-date for a currently-running run)
      2. SQLite-persisted rows (available after a server restart)
      3. Static _STAGE_DEFS defaults (fills in any missing stages / descriptions)

    For completed/published/pending_review runs, any stage that is still
    "pending" is upgraded to "done" — this covers old runs where only
    the Coordinator's DB row was written (the other 4 used only in-memory
    tracking that didn't survive a server restart).

    Read-only and side-effect free.
    """
    from backend.crew import _stage_registry, _STAGE_DEFS  # lazy import avoids circular dep

    _TERMINAL_STATUSES = {"completed", "pending_review", "published", "rejected"}

    _STAGE_DEFAULTS: List[Dict[str, Any]] = [
        {
            "stage_name":   name,
            "status":       "pending",
            "description":  desc,
            "started_at":   None,
            "completed_at": None,
        }
        for name, desc in _STAGE_DEFS
    ]
    _desc_map = dict(_STAGE_DEFS)

    try:
        # Build a merged map: start from static defaults, overlay with live data
        merged: dict[str, dict] = {d["stage_name"]: dict(d) for d in _STAGE_DEFAULTS}

        # Layer 1: DB-persisted rows
        db_rows = get_stage_log(run_id)
        for row in db_rows:
            name = row.get("stage_name", "")
            if name in merged:
                merged[name].update({k: v for k, v in row.items() if v is not None})
                # Always use the canonical static description — never an empty DB value
                if not merged[name].get("description"):
                    merged[name]["description"] = _desc_map.get(name, "")

        # Layer 2: In-memory registry (live, overrides DB for running runs)
        in_memory = _stage_registry.get(run_id, [])
        for entry in in_memory:
            name = entry.get("stage_name", "")
            if name in merged:
                merged[name].update({k: v for k, v in entry.items() if v is not None})
                if not merged[name].get("description"):
                    merged[name]["description"] = _desc_map.get(name, "")

        # Layer 3: For terminal-status runs, promote "pending" stages → "done"
        # This fixes old runs where only Coordinator wrote a DB row and the
        # other 4 stages' in-memory data was lost on server restart.
        run_data = get_run(run_id)
        run_status = run_data.get("metadata", {}).get("status", "") if run_data else ""
        if run_status in _TERMINAL_STATUSES and run_status != "failed":
            for entry in merged.values():
                if entry["status"] == "pending":
                    entry["status"] = "done"

        # Return in canonical order
        return [merged[name] for name, _ in _STAGE_DEFS if name in merged]

    except Exception as exc:
        logger.warning("Failed to retrieve stages for run %s: %s", run_id, exc)
        return _STAGE_DEFAULTS


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
    500 : DB update failed
    """
    try:
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

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to publish run %s", run_id)
        raise HTTPException(status_code=500, detail=f"Failed to publish run: {exc}") from exc


@app.post("/api/runs/{run_id}/reject", tags=["runs"])
async def reject_run(run_id: str, body: Optional[RejectRequest] = None) -> RejectResponse:
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
    500 : DB update failed
    """
    try:
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

        reason = ((body.reason if body else None) or "").strip() or None
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

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to reject run %s", run_id)
        raise HTTPException(status_code=500, detail=f"Failed to reject run: {exc}") from exc