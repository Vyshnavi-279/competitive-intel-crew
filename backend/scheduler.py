"""
backend/scheduler.py — APScheduler background job for weekly automated briefings.

WHY THIS EXISTS:
The product promise is a *weekly* competitive brief that lands in the
strategy org's inbox every Monday morning without anyone having to remember
to trigger it.  APScheduler's BackgroundScheduler runs inside the same
process as the FastAPI app (no separate worker/queue required) and fires
the crew run in a thread pool so the API remains fully responsive.

Weekly schedule:
    Every Monday at 08:00 server-local time.

Standing topics:
    Read from the ``STANDING_TOPICS`` environment variable as a
    comma-separated list.  If unset, a single illustrative default is used.
    Example .env entry:
        STANDING_TOPICS=AI developer tools market,Cloud infrastructure pricing,Open-source LLM landscape

Audit trail:
    Every scheduled run writes two audit_log entries:
        "scheduled run started for topic: <topic>"
        "scheduled run completed for topic: <topic>"   (or "failed …")
    The RunMetadata.triggered_by field is set to "scheduled" so the UI can
    render a distinguishing badge.

Usage (from main.py):
    from backend.scheduler import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()          # call during app startup
    ...
    scheduler.shutdown()       # call during app shutdown
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_DEFAULT_TOPIC = "AI developer tools and LLM infrastructure market"


def _load_standing_topics() -> List[str]:
    """Return the list of topics to brief every week.

    Reads ``STANDING_TOPICS`` from the environment (comma-separated).
    Falls back to a single illustrative default if the variable is unset
    or empty so the scheduler always has work to do.
    """
    raw = os.getenv("STANDING_TOPICS", "").strip()
    if not raw:
        logger.info(
            "STANDING_TOPICS not set — using default topic: %r", _DEFAULT_TOPIC
        )
        return [_DEFAULT_TOPIC]
    topics = [t.strip() for t in raw.split(",") if t.strip()]
    if not topics:
        return [_DEFAULT_TOPIC]
    logger.info("Standing topics loaded: %s", topics)
    return topics


# ---------------------------------------------------------------------------
# The job function — runs in APScheduler's thread-pool executor
# ---------------------------------------------------------------------------


def _run_scheduled_briefings() -> None:
    """Entry point called by APScheduler every Monday at 08:00.

    This function runs in a worker thread (not the async event loop), so it
    uses ``asyncio.run()`` to drive the async ``run_briefing`` coroutine.
    Each topic in STANDING_TOPICS is processed sequentially within the same
    weekly invocation so we don't hammer the LLM API with parallel requests.

    Failures on individual topics are caught and logged; other topics still
    run.  The scheduler job itself never raises so APScheduler doesn't
    permanently disable the trigger.
    """
    # Import here (not at module top) to avoid circular imports at startup.
    # Both modules are fully initialised by the time the job fires.
    from backend.crew import run_briefing
    from backend.storage.db import log_event, save_run

    topics = _load_standing_topics()
    logger.info(
        "[scheduler] Weekly run triggered — %d topic(s) to process", len(topics)
    )

    for topic in topics:
        logger.info("[scheduler] Starting briefing for topic: %r", topic)
        try:
            # run_briefing is an async coroutine; drive it synchronously.
            briefing = asyncio.run(run_briefing(topic, triggered_by="scheduled"))

            run_id = briefing.metadata.run_id

            # Persist the briefing before writing audit entries (FK constraint).
            save_run(briefing)

            log_event(run_id, f"scheduled run started for topic: {topic}")

            if briefing.metadata.status == "failed":
                log_event(
                    run_id,
                    f"scheduled run failed for topic: {topic}",
                )
                logger.warning(
                    "[scheduler] Briefing failed for topic %r (run_id=%s)",
                    topic,
                    run_id,
                )
            else:
                log_event(
                    run_id,
                    f"scheduled run completed for topic: {topic}",
                )
                logger.info(
                    "[scheduler] Briefing completed for topic %r "
                    "(run_id=%s, status=%s, duration=%.1fs)",
                    topic,
                    run_id,
                    briefing.metadata.status,
                    briefing.metadata.duration_seconds or 0,
                )

        except Exception as exc:
            # Catch-all so one bad topic never blocks the rest or kills the
            # scheduler trigger.
            logger.error(
                "[scheduler] Unhandled error processing topic %r: %s",
                topic,
                exc,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------


def create_scheduler() -> BackgroundScheduler:
    """Build and configure the BackgroundScheduler instance.

    The caller (``backend/main.py``) is responsible for calling
    ``scheduler.start()`` and ``scheduler.shutdown()``.

    Schedule: CronTrigger fires every Monday (day_of_week=0) at 08:00
    server-local time.  To adjust the schedule without code changes, set:
        SCHEDULER_DAY_OF_WEEK  (default: "mon")
        SCHEDULER_HOUR         (default: "8")
        SCHEDULER_MINUTE       (default: "0")
    """
    day_of_week = os.getenv("SCHEDULER_DAY_OF_WEEK", "mon")
    hour = os.getenv("SCHEDULER_HOUR", "8")
    minute = os.getenv("SCHEDULER_MINUTE", "0")

    scheduler = BackgroundScheduler(
        job_defaults={
            # If a fire time is missed (e.g. server was down), don't run
            # catch-up jobs automatically — the next Monday is fine.
            "misfire_grace_time": 3600,  # 1-hour grace window
            "coalesce": True,            # collapse multiple missed fires into one
            "max_instances": 1,          # never run two weekly jobs concurrently
        }
    )

    scheduler.add_job(
        func=_run_scheduled_briefings,
        trigger=CronTrigger(
            day_of_week=day_of_week,
            hour=int(hour),
            minute=int(minute),
        ),
        id="weekly_briefing",
        name="Weekly Competitive Intelligence Briefings",
        replace_existing=True,
    )

    logger.info(
        "[scheduler] Weekly briefing job scheduled: every %s at %s:%s",
        day_of_week,
        hour,
        minute.zfill(2),
    )
    return scheduler
