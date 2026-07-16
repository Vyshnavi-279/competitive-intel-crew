"""
backend/logging_config.py — centralised logging setup for MarketPulse.

WHAT THIS MODULE DOES
---------------------
Configures Python's stdlib logging so that every module in the backend
emits structured, consistently formatted log lines to:

  1. Console (stderr)  — human-readable coloured output in development;
                         plain JSON-like lines in production (Render).
  2. Log files         — one rotating file per concern, written to LOG_DIR:
       backend/logs/app.log        — everything INFO and above
       backend/logs/errors.log     — ERROR and CRITICAL only
       backend/logs/runs.log       — per-run lifecycle events (start / end / fail)
       backend/logs/llm.log        — every LLM call (model, tokens, latency)
       backend/logs/tools.log      — SafeSearchTool calls and cache hits
       backend/logs/governance.log — citation_guard and flag_unverified events
       backend/logs/scheduler.log  — APScheduler job fires and outcomes

HOW TO USE
----------
Import and call setup_logging() once at application startup, before any
other module logs anything:

    # in backend/main.py lifespan:
    from backend.logging_config import setup_logging
    setup_logging()

After that, every module just does:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("message")

The logger name (__name__) is used to route log records to the correct
file handler automatically.

LOG LEVELS
----------
  DEBUG   — fine-grained diagnostic info (LLM request payloads, cache keys)
  INFO    — normal operational events (run started, stage completed)
  WARNING — unexpected but recoverable (rate-limit retry, missing citation)
  ERROR   — failures that degraded the output (run failed, API error)
  CRITICAL— failures that need immediate attention (DB corrupt, bad startup)

CONFIGURATION VIA ENV VARS
---------------------------
  LOG_LEVEL   — root log level (default: INFO)
                Set to DEBUG for verbose LLM/tool tracing.
  LOG_DIR     — directory for log files (default: backend/logs)
                Set to /data/logs on Render to persist across deploys.
  LOG_TO_FILE — write to log files (default: true)
                Set to false in CI/test environments.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path
from typing import Optional


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_LOG_DIR   = Path(__file__).parent / "logs"
DEFAULT_LOG_LEVEL = "INFO"

# Maximum size of each rotating log file before it rolls over.
_MAX_BYTES    = 5 * 1024 * 1024   # 5 MB
_BACKUP_COUNT = 5                  # keep 5 rotated files → max 25 MB per log


# ── Formatters ───────────────────────────────────────────────────────────────

class _ConsoleFormatter(logging.Formatter):
    """
    Human-readable formatter for the console handler.

    Format:  HH:MM:SS.mmm LEVEL     logger_name  message
    Example: 20:14:03.412 INFO      backend.crew  Coordinator stage started

    Uses ANSI colour codes in development (when stderr is a TTY).
    Falls back to plain text on Render / CI where stderr is piped.
    """

    _GREY   = "\033[90m"
    _GREEN  = "\033[32m"
    _YELLOW = "\033[33m"
    _RED    = "\033[31m"
    _BOLD   = "\033[1m"
    _RESET  = "\033[0m"

    _LEVEL_COLOURS = {
        "DEBUG":    "\033[90m",   # grey
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[1;31m", # bold red
    }

    def __init__(self, use_colour: bool = True) -> None:
        super().__init__()
        self._use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        # Millisecond-precision timestamp
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        ms = int(record.msecs)
        timestamp = f"{ts}.{ms:03d}"

        level = record.levelname
        name  = record.name[:30]           # truncate long names
        msg   = record.getMessage()

        if record.exc_info:
            msg = msg + "\n" + self.formatException(record.exc_info)

        if self._use_colour:
            colour = self._LEVEL_COLOURS.get(level, "")
            return (
                f"{self._GREY}{timestamp}{self._RESET} "
                f"{colour}{level:<8}{self._RESET} "
                f"{self._GREY}{name:<30}{self._RESET} "
                f"{msg}"
            )
        return f"{timestamp} {level:<8} {name:<30} {msg}"


class _FileFormatter(logging.Formatter):
    """
    Structured plain-text formatter for log files.

    Format:  ISO-8601 | LEVEL | logger_name | message [| exc_info]
    Example: 2026-07-16T20:14:03.412+0530 | INFO | backend.crew | Coordinator stage started

    Plain text (not JSON) so logs are grep-friendly without a JSON parser.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts  = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        ms  = int(record.msecs)
        ts  = f"{ts}.{ms:03d}"
        msg = record.getMessage()
        line = f"{ts} | {record.levelname:<8} | {record.name} | {msg}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# ── Handler factory ──────────────────────────────────────────────────────────

def _rotating_handler(
    path: Path,
    level: int,
    formatter: logging.Formatter,
) -> logging.handlers.RotatingFileHandler:
    """Create a size-rotating file handler at *path* with *level* and *formatter*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        filename    = str(path),
        maxBytes    = _MAX_BYTES,
        backupCount = _BACKUP_COUNT,
        encoding    = "utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


# ── Name-based routing filters ────────────────────────────────────────────────

class _NameFilter(logging.Filter):
    """Pass only records whose logger name starts with any of *prefixes*."""

    def __init__(self, *prefixes: str) -> None:
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return any(record.name.startswith(p) for p in self._prefixes)


class _ExcludeFilter(logging.Filter):
    """Block records whose logger name starts with any of *prefixes*."""

    def __init__(self, *prefixes: str) -> None:
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(record.name.startswith(p) for p in self._prefixes)


# ── Public API ────────────────────────────────────────────────────────────────

def setup_logging(
    log_level: Optional[str] = None,
    log_dir: Optional[Path]  = None,
    log_to_file: Optional[bool] = None,
) -> None:
    """
    Configure all logging handlers for the MarketPulse backend.

    Parameters
    ----------
    log_level
        Root log level string ("DEBUG", "INFO", "WARNING", "ERROR").
        Defaults to the LOG_LEVEL env var, or "INFO" if not set.
    log_dir
        Directory to write rotating log files into.
        Defaults to LOG_DIR env var, or backend/logs/.
    log_to_file
        Write to log files.  Defaults to LOG_TO_FILE env var ("true"/"false"),
        or True if not set.  Set to False in CI to avoid creating log files.

    This function is idempotent — calling it multiple times is safe (handlers
    are not duplicated because we clear root handlers first).
    """

    # ── Resolve config from env vars / arguments ─────────────────────────────
    level_str = (
        log_level
        or os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    ).upper()
    level = getattr(logging, level_str, logging.INFO)

    write_files = log_to_file
    if write_files is None:
        write_files = os.getenv("LOG_TO_FILE", "true").lower() not in ("false", "0", "no")

    log_dir_path = log_dir or Path(os.getenv("LOG_DIR", str(DEFAULT_LOG_DIR)))

    # ── Formatters ────────────────────────────────────────────────────────────
    use_colour = sys.stderr.isatty()
    console_fmt = _ConsoleFormatter(use_colour=use_colour)
    file_fmt    = _FileFormatter()

    # ── Root logger ───────────────────────────────────────────────────────────
    root = logging.getLogger()
    root.handlers.clear()          # prevent duplicate handlers on reload
    root.setLevel(level)

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_fmt)
    # Silence noisy third-party loggers on the console
    console_handler.addFilter(
        _ExcludeFilter("LiteLLM", "httpx", "httpcore", "urllib3", "multipart")
    )
    root.addHandler(console_handler)

    if not write_files:
        return

    # ── app.log — everything INFO+ from first-party code ─────────────────────
    app_handler = _rotating_handler(
        log_dir_path / "app.log",
        logging.INFO,
        file_fmt,
    )
    app_handler.addFilter(_NameFilter("backend", "eval"))
    root.addHandler(app_handler)

    # ── errors.log — ERROR+ from anywhere ────────────────────────────────────
    error_handler = _rotating_handler(
        log_dir_path / "errors.log",
        logging.ERROR,
        file_fmt,
    )
    root.addHandler(error_handler)

    # ── runs.log — run lifecycle events ──────────────────────────────────────
    # Catches log records from backend.crew (run_briefing start/end/fail)
    # and backend.main (API request for /api/run).
    runs_handler = _rotating_handler(
        log_dir_path / "runs.log",
        logging.INFO,
        file_fmt,
    )
    runs_handler.addFilter(_NameFilter("backend.crew", "backend.main"))
    root.addHandler(runs_handler)

    # ── llm.log — every LLM call via litellm ─────────────────────────────────
    # LiteLLM logs each call at DEBUG under the "LiteLLM" logger name.
    # We capture those here at DEBUG so you can review exact token counts
    # and latency per model call without flooding the console.
    llm_handler = _rotating_handler(
        log_dir_path / "llm.log",
        logging.DEBUG,
        file_fmt,
    )
    llm_handler.addFilter(_NameFilter("LiteLLM", "litellm", "crewai.llm"))
    root.addHandler(llm_handler)
    # Allow LiteLLM's own logger to emit at DEBUG (it defaults to WARNING).
    logging.getLogger("LiteLLM").setLevel(logging.DEBUG)
    logging.getLogger("litellm").setLevel(logging.DEBUG)

    # ── tools.log — SafeSearchTool calls and cache events ────────────────────
    tools_handler = _rotating_handler(
        log_dir_path / "tools.log",
        logging.DEBUG,
        file_fmt,
    )
    tools_handler.addFilter(_NameFilter("backend.tools"))
    root.addHandler(tools_handler)

    # ── governance.log — citation guard and assertion flag events ────────────
    governance_handler = _rotating_handler(
        log_dir_path / "governance.log",
        logging.INFO,
        file_fmt,
    )
    governance_handler.addFilter(_NameFilter("backend.governance"))
    root.addHandler(governance_handler)

    # ── scheduler.log — APScheduler job fire events ───────────────────────────
    scheduler_handler = _rotating_handler(
        log_dir_path / "scheduler.log",
        logging.INFO,
        file_fmt,
    )
    scheduler_handler.addFilter(_NameFilter("backend.scheduler", "apscheduler"))
    root.addHandler(scheduler_handler)

    # ── Quiet noisy third-party loggers ──────────────────────────────────────
    # These emit debug/info noise that is not useful in normal operation.
    for noisy in (
        "httpx", "httpcore", "urllib3", "multipart",
        "chromadb", "opentelemetry", "grpc",
        "crewai.telemetry", "posthog",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("backend.logging_config").info(
        "Logging configured — level=%s files=%s dir=%s",
        level_str, write_files, log_dir_path,
    )
