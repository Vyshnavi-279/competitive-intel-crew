"""
backend/storage/db.py — SQLite persistence layer for competitive-intel runs.

Tables
------
runs
    run_id            TEXT  PRIMARY KEY
    topic             TEXT  NOT NULL
    started_at        TEXT  NOT NULL  (ISO-8601 UTC)
    duration_seconds  REAL
    sources_attempted INTEGER
    sources_used      INTEGER
    total_steps       INTEGER
    status            TEXT  NOT NULL
    triggered_by      TEXT  NOT NULL DEFAULT 'manual'   ← who/what started the run
    briefing_json     TEXT  NOT NULL  (full JSON blob from Briefing.to_dict())

audit_log
    id         INTEGER PRIMARY KEY AUTOINCREMENT
    run_id     TEXT    NOT NULL  REFERENCES runs(run_id)
    event_text TEXT    NOT NULL
    timestamp  TEXT    NOT NULL  (ISO-8601 UTC)

`init_db()` is called at module import time so the file and tables are
created automatically the first time any other module imports this one.
Migration safety: `triggered_by` is added via ALTER TABLE IF NOT EXISTS
(guarded by a try/except) so existing databases are upgraded in-place
without data loss.

DB location
-----------
Set DB_DIR env var to control where runs.db is written. On Render/Railway,
point this at a mounted persistent volume (e.g. DB_DIR=/data) so the
database survives restarts and redeploys — the default (next to this file)
lives on ephemeral disk and will be wiped on every redeploy otherwise.
"""

from __future__ import annotations

import json
import os  # <-- Moved to the absolute top of standard imports
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

# Safe import to prevent circular dependency loops
if TYPE_CHECKING:
    from backend.models.schemas import Briefing

# ---------------------------------------------------------------------------
# Database path
# ---------------------------------------------------------------------------

# os is now fully defined when this line runs!
_DB_DIR = Path(os.environ.get("DB_DIR", Path(__file__).parent))
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "runs.db"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _connect() -> sqlite3.Connection:
    """Open a connection with row_factory set to dict-like Row objects."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce FK constraints (SQLite disables them by default).
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _utcnow() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create the database file and tables if they don't already exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS so
    re-importing this module never clobbers existing data.

    Migration: if the `triggered_by` column is missing from an existing
    `runs` table (databases created before this field was added), it is
    added automatically with a default of 'manual'.
    """
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id            TEXT PRIMARY KEY,
                topic             TEXT NOT NULL,
                started_at        TEXT NOT NULL,
                duration_seconds  REAL,
                sources_attempted INTEGER NOT NULL DEFAULT 0,
                sources_used      INTEGER NOT NULL DEFAULT 0,
                total_steps       INTEGER NOT NULL DEFAULT 0,
                status            TEXT NOT NULL,
                triggered_by      TEXT NOT NULL DEFAULT 'manual',
                briefing_json     TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id     TEXT NOT NULL REFERENCES runs(run_id),
                event_text TEXT NOT NULL,
                timestamp  TEXT NOT NULL
            )
            """
        )
        # PHASE 1 ADDITION — stage_log: tracks per-stage progress for the
        # 5-agent pipeline so the frontend can render a live stepper.
        # Additive only — does not touch runs or audit_log definitions.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stage_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       TEXT    NOT NULL,
                stage_name   TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'pending',
                description  TEXT    NOT NULL DEFAULT '',
                started_at   TEXT,
                completed_at TEXT
            )
            """
        )
        # PHASE 2 ADDITION — search_cache: avoids re-spending the search
        # budget on a query we've already run within the last 7 days.
        # query_normalized is the PRIMARY KEY so duplicate inserts are safe.
        # Additive only — does not touch any existing table definitions.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
                query_normalized TEXT PRIMARY KEY,
                result_json      TEXT NOT NULL,
                source_name      TEXT NOT NULL DEFAULT '',
                fetched_at       TEXT NOT NULL
            )
            """
        )
        conn.commit()

        # Migration guard: add triggered_by to pre-existing databases.
        # SQLite does not support IF NOT EXISTS on ALTER TABLE, so we catch
        # the OperationalError that fires when the column already exists.
        try:
            conn.execute(
                "ALTER TABLE runs ADD COLUMN triggered_by TEXT NOT NULL DEFAULT 'manual'"
            )
            conn.commit()
        except sqlite3.OperationalError:
            # Column already present — nothing to do.
            pass

        # PHASE 4 ADDITION — additive migration: add submitted_by column.
        # Nullable so existing rows (which have no value) default to NULL
        # rather than requiring a non-null default that could mask data.
        try:
            conn.execute(
                "ALTER TABLE runs ADD COLUMN submitted_by TEXT"
            )
            conn.commit()
        except sqlite3.OperationalError:
            # Column already present — nothing to do.
            pass


def save_run(briefing: Briefing) -> None:
    """Persist a completed (or failed) Briefing to the runs table.

    If a row with the same run_id already exists it is replaced, so
    calling save_run twice on the same object (e.g. after a status update)
    is safe.

    Parameters
    ----------
    briefing:
        A fully-populated Briefing.  briefing.to_dict() is serialised to
        JSON and stored in the briefing_json column.
    """
    m = briefing.metadata
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO runs
                (run_id, topic, started_at, duration_seconds,
                 sources_attempted, sources_used, total_steps,
                 status, triggered_by, submitted_by, briefing_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.run_id,
                m.topic,
                m.started_at.isoformat(),
                m.duration_seconds,
                m.sources_attempted,
                m.sources_used,
                m.total_steps,
                m.status,
                m.triggered_by,
                getattr(m, "submitted_by", None),  # PHASE 4: nullable
                json.dumps(briefing.to_dict()),
            ),
        )
        conn.commit()


def delete_run(run_id: str) -> bool:
    """Delete a run and its audit log entries.

    Returns True if the run existed and was deleted, False if not found.
    """
    with _connect() as conn:
        conn.execute("DELETE FROM audit_log WHERE run_id = ?", (run_id,))
        cursor = conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        conn.commit()
    return cursor.rowcount > 0


def delete_failed_runs() -> int:
    """Delete all runs with status='failed'. Returns count deleted."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT run_id FROM runs WHERE status = 'failed'"
        ).fetchall()
        run_ids = [r["run_id"] for r in rows]
        for rid in run_ids:
            conn.execute("DELETE FROM audit_log WHERE run_id = ?", (rid,))
        cursor = conn.execute("DELETE FROM runs WHERE status = 'failed'")
        conn.commit()
    return cursor.rowcount


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Return the full briefing dict for *run_id*, or None if not found.

    The returned dict is the deserialised briefing_json blob — ready to
    be returned directly from a FastAPI route as JSON.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT briefing_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["briefing_json"])


def list_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """Return lightweight summaries of the most recent runs.

    Each summary contains the fields useful for a dashboard run-history
    list.  The full briefing_json is intentionally excluded to keep
    response size small.

    Includes `triggered_by` so the UI can show a "⏱ Scheduled" badge next
    to automated runs.

    Parameters
    ----------
    limit:
        Maximum number of rows to return, newest first.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT run_id, topic, started_at, status,
                   sources_used, sources_attempted, triggered_by,
                   duration_seconds
            FROM   runs
            ORDER  BY started_at DESC
            LIMIT  ?
            """,
            (limit,),
        ).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        # Derive sources_skipped_count from the difference so the caller
        # doesn't need to parse the full briefing blob.
        d["sources_skipped_count"] = (
            d.pop("sources_attempted", 0) - d.get("sources_used", 0)
        )
        result.append(d)
    return result


def update_run_status(run_id: str, status: str) -> bool:
    """Update the status column for *run_id* and patch it inside briefing_json.

    Returns True if a row was updated, False if run_id was not found.
    Used by the publish and reject endpoints.

    Both the `status` column AND the `briefing_json` blob are updated so that
    subsequent calls to ``get_run()`` return the current status rather than
    the stale value baked into the JSON at save time.
    """
    with _connect() as conn:
        # Fetch the current briefing_json to patch the status inside it.
        row = conn.execute(
            "SELECT briefing_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return False

        try:
            blob = json.loads(row["briefing_json"])
            if "metadata" in blob:
                blob["metadata"]["status"] = status
            updated_json = json.dumps(blob)
        except Exception:
            # If JSON parsing fails for any reason, update the column only.
            updated_json = row["briefing_json"]

        cursor = conn.execute(
            "UPDATE runs SET status = ?, briefing_json = ? WHERE run_id = ?",
            (status, updated_json, run_id),
        )
        conn.commit()
    return cursor.rowcount > 0


def log_event(run_id: str, event_text: str) -> None:
    """Append an entry to the audit_log for *run_id*.

    Parameters
    ----------
    run_id:
        Must match an existing run in the runs table (FK constraint).
    event_text:
        Human-readable description of the event (e.g. "run started",
        "run completed", "published by reviewer",
        "scheduled run completed for topic: X").
    """
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (run_id, event_text, timestamp) VALUES (?, ?, ?)",
            (run_id, event_text, _utcnow()),
        )
        conn.commit()


def get_kpis() -> Dict[str, Any]:
    """Compute 5 business KPIs from the runs table.

    KPIs
    ----
    1. run_success_rate      — % of runs that reached pending_review/published/rejected
                               (i.e. did not fail), out of all finished runs.
    2. citation_rate         — average fraction of claims that carry at least one
                               citation across all non-failed runs (from briefing_json).
    3. source_coverage       — average sources_used per completed run.
    4. avg_duration_seconds  — mean wall-clock run time for completed runs.
    5. publish_rate          — % of pending_review+published+rejected runs that were
                               ultimately published.

    Returns a dict safe to serialise directly as JSON.
    """
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT run_id, status, sources_used, duration_seconds, briefing_json
            FROM   runs
            ORDER  BY started_at DESC
            LIMIT  200
            """
        ).fetchall()

    if not rows:
        return {
            "run_success_rate": 0.0,
            "citation_rate": 0.0,
            "source_coverage": 0.0,
            "avg_duration_seconds": 0.0,
            "publish_rate": 0.0,
            "total_runs": 0,
        }

    total = len(rows)
    successful = [r for r in rows if r["status"] in ("pending_review", "published", "rejected")]
    failed = [r for r in rows if r["status"] == "failed"]
    published = [r for r in rows if r["status"] == "published"]
    reviewable = [r for r in rows if r["status"] in ("pending_review", "published", "rejected")]

    # KPI 1 — run success rate
    finished = [r for r in rows if r["status"] != "running"]
    run_success_rate = (len(successful) / len(finished) * 100) if finished else 0.0

    # KPI 2 — citation rate (avg % of claims with citations across briefings)
    citation_rates: list[float] = []
    for row in successful:
        try:
            data = json.loads(row["briefing_json"])
            sections = data.get("sections", [])
            total_claims = sum(len(s.get("claims", [])) for s in sections)
            cited_claims = sum(
                1
                for s in sections
                for c in s.get("claims", [])
                if c.get("citations")
            )
            if total_claims > 0:
                citation_rates.append(cited_claims / total_claims * 100)
        except Exception:
            pass
    citation_rate = sum(citation_rates) / len(citation_rates) if citation_rates else 0.0

    # KPI 3 — avg sources used per successful run
    sources = [r["sources_used"] for r in successful if r["sources_used"] is not None]
    source_coverage = sum(sources) / len(sources) if sources else 0.0

    # KPI 4 — avg duration
    durations = [
        r["duration_seconds"]
        for r in successful
        if r["duration_seconds"] is not None
    ]
    avg_duration = sum(durations) / len(durations) if durations else 0.0

    # KPI 5 — publish rate (of runs that went through review)
    publish_rate = (len(published) / len(reviewable) * 100) if reviewable else 0.0

    return {
        "run_success_rate": round(run_success_rate, 1),
        "citation_rate": round(citation_rate, 1),
        "source_coverage": round(source_coverage, 1),
        "avg_duration_seconds": round(avg_duration, 1),
        "publish_rate": round(publish_rate, 1),
        "total_runs": total,
        "successful_runs": len(successful),
        "failed_runs": len(failed),
        "published_runs": len(published),
    }


# ---------------------------------------------------------------------------
# PHASE 4 ADDITION — usage analytics helper
# ---------------------------------------------------------------------------


def get_usage_analytics() -> Dict[str, Any]:
    """Return per-analyst usage stats and a 30-day daily run trend.

    Returns
    -------
    {
      "by_user": [
          {"submitted_by": str, "run_count": int, "avg_duration_seconds": float}
      ],
      "daily_trend": [
          {"date": "YYYY-MM-DD", "run_count": int}   -- last 30 days
      ]
    }

    All errors are caught so a DB problem never breaks the API response.
    """
    try:
        with _connect() as conn:
            # Per-user aggregates (coalesce NULL submitted_by → 'default_user')
            user_rows = conn.execute(
                """
                SELECT
                    COALESCE(submitted_by, 'default_user') AS submitted_by,
                    COUNT(*) AS run_count,
                    AVG(CASE WHEN duration_seconds IS NOT NULL THEN duration_seconds END)
                        AS avg_duration_seconds
                FROM runs
                GROUP BY COALESCE(submitted_by, 'default_user')
                ORDER BY run_count DESC
                """
            ).fetchall()

            # Daily run counts over the last 30 calendar days
            daily_rows = conn.execute(
                """
                SELECT
                    DATE(started_at) AS date,
                    COUNT(*) AS run_count
                FROM runs
                WHERE started_at >= DATE('now', '-30 days')
                GROUP BY DATE(started_at)
                ORDER BY date ASC
                """
            ).fetchall()

        by_user = [
            {
                "submitted_by": r["submitted_by"],
                "run_count": r["run_count"],
                "avg_duration_seconds": round(r["avg_duration_seconds"] or 0, 1),
            }
            for r in user_rows
        ]

        daily_trend = [
            {"date": r["date"], "run_count": r["run_count"]}
            for r in daily_rows
        ]

        return {"by_user": by_user, "daily_trend": daily_trend}

    except Exception:
        return {"by_user": [], "daily_trend": []}


# ---------------------------------------------------------------------------
# PHASE 2 ADDITION — search_cache helpers
# ---------------------------------------------------------------------------

_CACHE_TTL_DAYS = 7  # cached results older than this are treated as a miss


def _normalize_query(query: str) -> str:
    """Lowercase + strip whitespace for cache key normalisation."""
    return query.lower().strip()


def get_cached_search(query: str) -> Optional[str]:
    """Return cached result JSON for *query*, or None on miss / expired.

    A result is considered expired if its fetched_at is older than
    _CACHE_TTL_DAYS days.  Any DB error falls through to None so the caller
    always falls back to a real search.
    """
    try:
        key = _normalize_query(query)
        with _connect() as conn:
            row = conn.execute(
                "SELECT result_json, fetched_at FROM search_cache WHERE query_normalized = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        # TTL check
        fetched_at_str = row["fetched_at"]
        fetched_dt = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - fetched_dt).days
        if age_days > _CACHE_TTL_DAYS:
            return None  # expired — caller will run a real search
        return row["result_json"]
    except Exception:
        return None  # any error → treat as a miss, never block a real search


def save_cached_search(query: str, result_json: str, source_name: str = "") -> None:
    """Persist a search result to the cache.

    Uses INSERT OR REPLACE so calling this twice for the same normalised
    query refreshes the TTL rather than leaving a stale row.
    Any DB error is silently swallowed — cache writes must never break a run.
    """
    try:
        key = _normalize_query(query)
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO search_cache
                    (query_normalized, result_json, source_name, fetched_at)
                VALUES (?, ?, ?, ?)
                """,
                (key, result_json, source_name or "", _utcnow()),
            )
            conn.commit()
    except Exception:
        pass  # cache write failures are silent


# ---------------------------------------------------------------------------
# PHASE 1 ADDITION — stage_log helpers
# ---------------------------------------------------------------------------


def save_stage_start(run_id: str, stage_name: str, description: str) -> None:
    """Insert or update a stage_log row to status='running'.

    Safe to call multiple times for the same (run_id, stage_name) pair —
    uses INSERT OR REPLACE so a retry doesn't leave duplicate rows.
    Wrapped in try/except at the call site in crew.py, but also defensively
    here so a DB error never propagates into the crew pipeline.
    """
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO stage_log
                    (run_id, stage_name, status, description, started_at, completed_at)
                VALUES (?, ?, 'running', ?, ?, NULL)
                """,
                (run_id, stage_name, description, _utcnow()),
            )
            conn.commit()
    except Exception:
        pass  # stage tracking must never crash the pipeline


def save_stage_end(run_id: str, stage_name: str, status: str = "done") -> None:
    """Mark a stage as done (or failed) with a completed_at timestamp."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE stage_log
                   SET status = ?, completed_at = ?
                 WHERE run_id = ? AND stage_name = ?
                """,
                (status, _utcnow(), run_id, stage_name),
            )
            conn.commit()
    except Exception:
        pass  # stage tracking must never crash the pipeline


def get_stage_log(run_id: str) -> List[Dict[str, Any]]:
    """Return ordered stage_log rows for a run as plain dicts.

    Returns an empty list if the run_id has no rows (normal before any stages
    have started).
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT stage_name, status, description, started_at, completed_at
                  FROM stage_log
                 WHERE run_id = ?
                 ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Auto-initialise on import
# ---------------------------------------------------------------------------

init_db()