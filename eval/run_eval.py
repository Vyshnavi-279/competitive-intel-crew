"""
eval/run_eval.py — Evaluation harness for the Competitive Intel Crew.

Runs the full pytest suite in eval/test_scenarios.py, captures per-scenario
pass/fail and timing, then writes a Markdown report to eval/eval_report.md.

Usage
-----
    # From the project root:
    python eval/run_eval.py

    # Or from inside eval/:
    python run_eval.py

The script exits with code 0 if all tests pass, 1 if any fail.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Path setup — allow imports from the project root regardless of cwd
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent.resolve()          # eval/
_PROJECT_ROOT = _SCRIPT_DIR.parent.resolve()            # competitive-intel-crew/
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Scenario metadata
# Each entry maps the pytest node-id suffix to its human description and layer.
# ---------------------------------------------------------------------------

@dataclass
class ScenarioMeta:
    """Static metadata for a single evaluation scenario."""
    node_id_fragment: str   # Matches the test function / class name in node-id
    label: str              # Short human label for the report table
    layer: str              # Evaluation layer label (matches course slide taxonomy)
    description: str        # One-sentence description for the Notes column


_SCENARIOS: List[ScenarioMeta] = [
    ScenarioMeta(
        node_id_fragment="test_full_weekly_briefing_happy_path",
        label="Happy-path briefing",
        layer="Trace + full pipeline",
        description="POST /api/run returns 200, 3 correctly-ordered sections, every claim cited.",
    ),
    ScenarioMeta(
        node_id_fragment="test_source_failure_handling",
        label="Source failure handling",
        layer="Failure-handling",
        description="Mid-run source exceptions → run completes, sources_skipped non-empty.",
    ),
    ScenarioMeta(
        node_id_fragment="test_uncited_claim_is_dropped",
        label="Uncited claim dropped",
        layer="Governance / output",
        description="enforce_citations removes zero-citation claims and flags them.",
    ),
    ScenarioMeta(
        node_id_fragment="test_runaway_guard_respects_cap",
        label="Runaway guard cap",
        layer="Trace / reliability",
        description="SafeSearchTool refuses calls beyond MAX_SOURCES without raising.",
    ),
    ScenarioMeta(
        node_id_fragment="test_planted_unverified_claim_is_hedged",
        label="Sensational claim hedged",
        layer="Adversarial / governance",
        description="flag_unverified_assertions prefixes single-source high-risk claim with 'Unverified:'.",
    ),
]

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    """Outcome of a single scenario after running pytest."""
    meta: ScenarioMeta
    passed: bool = False
    duration_seconds: float = 0.0
    notes: str = ""
    error_excerpt: str = ""


# ---------------------------------------------------------------------------
# Pytest plugin — collects per-test timing and outcome
# ---------------------------------------------------------------------------


class _ResultCollector:
    """Minimal pytest plugin that records pass/fail and wall-clock time per test."""

    def __init__(self) -> None:
        self.outcomes: dict[str, dict] = {}  # node_id → {passed, duration, longrepr}
        self._start_times: dict[str, float] = {}

    # ---- hooks ----------------------------------------------------------------

    def pytest_runtest_logstart(self, nodeid: str, location) -> None:
        self._start_times[nodeid] = time.perf_counter()

    def pytest_runtest_logreport(self, report) -> None:
        if report.when != "call":
            # We only care about the call phase (not setup/teardown).
            return
        nodeid = report.nodeid
        elapsed = time.perf_counter() - self._start_times.get(nodeid, time.perf_counter())
        longrepr = ""
        if report.failed and report.longrepr:
            # Capture a short excerpt of the failure traceback.
            full = str(report.longrepr)
            lines = full.splitlines()
            longrepr = "\n".join(lines[-10:])  # last 10 lines are usually the assertion
        self.outcomes[nodeid] = {
            "passed": report.passed,
            "duration": round(elapsed, 3),
            "longrepr": longrepr,
        }


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def run_eval(
    test_file: Optional[Path] = None,
    report_path: Optional[Path] = None,
    extra_pytest_args: Optional[List[str]] = None,
) -> int:
    """Run the pytest suite and write a Markdown report.

    Parameters
    ----------
    test_file:
        Path to the test file.  Defaults to eval/test_scenarios.py.
    report_path:
        Where to write eval_report.md.  Defaults to eval/eval_report.md.
    extra_pytest_args:
        Additional flags forwarded to pytest.main (e.g. ["-v"]).

    Returns
    -------
    int
        0 if all tests pass, 1 otherwise.
    """
    import pytest

    test_file = test_file or (_SCRIPT_DIR / "test_scenarios.py")
    report_path = report_path or (_SCRIPT_DIR / "eval_report.md")

    if not test_file.exists():
        print(f"[run_eval] ERROR: test file not found: {test_file}", file=sys.stderr)
        return 1

    collector = _ResultCollector()

    args = [
        str(test_file),
        "--tb=short",          # short tracebacks in the terminal
        "-q",                  # quiet mode — less noise
        "--no-header",
        f"--rootdir={_PROJECT_ROOT}",
    ]
    if extra_pytest_args:
        args.extend(extra_pytest_args)

    print(f"\n{'='*70}")
    print("  Competitive Intel Crew — Evaluation Suite")
    print(f"{'='*70}\n")

    suite_start = time.perf_counter()
    exit_code = pytest.main(args, plugins=[collector])
    suite_duration = time.perf_counter() - suite_start

    # ---- Map raw pytest outcomes back to ScenarioMeta ----------------------
    results: List[ScenarioResult] = []
    for meta in _SCENARIOS:
        # Find the matching node_id (may be class::method or just the function).
        matched_key = None
        for node_id in collector.outcomes:
            if meta.node_id_fragment in node_id:
                matched_key = node_id
                break

        if matched_key is None:
            # Test was never collected (import error, skipped, etc.)
            results.append(
                ScenarioResult(
                    meta=meta,
                    passed=False,
                    duration_seconds=0.0,
                    notes="Not collected — possible import or collection error.",
                )
            )
        else:
            outcome = collector.outcomes[matched_key]
            excerpt = outcome["longrepr"]
            # Truncate long excerpts for the report.
            if len(excerpt) > 300:
                excerpt = excerpt[:300] + " …[truncated]"
            results.append(
                ScenarioResult(
                    meta=meta,
                    passed=outcome["passed"],
                    duration_seconds=outcome["duration"],
                    notes=meta.description,
                    error_excerpt=excerpt,
                )
            )

    # ---- Write the Markdown report ----------------------------------------
    _write_report(results, report_path, suite_duration)

    # ---- Console summary ---------------------------------------------------
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    print(f"\n{'='*70}")
    print(f"  Results: {passed_count}/{total_count} passed  |  "
          f"Total time: {suite_duration:.2f}s")
    print(f"  Report written to: {report_path}")
    print(f"{'='*70}\n")

    return 0 if exit_code == 0 else 1


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------


def _write_report(
    results: List[ScenarioResult],
    path: Path,
    suite_duration: float,
) -> None:
    """Render results as a Markdown file at *path*."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    overall = "✅ ALL PASS" if passed == total else f"❌ {total - passed} FAILED"

    lines: List[str] = []

    # ── Header ───────────────────────────────────────────────────────────────
    lines += [
        "# Competitive Intel Crew — Evaluation Report",
        "",
        f"**Run at:** {now}  ",
        f"**Overall:** {overall}  ",
        f"**Suite duration:** {suite_duration:.2f}s  ",
        f"**Scenarios:** {passed}/{total} passed",
        "",
    ]

    # ── Results table ────────────────────────────────────────────────────────
    lines += [
        "## Scenario Results",
        "",
        "| # | Scenario | Layer | Result | Time (s) | Notes |",
        "|---|----------|-------|--------|----------|-------|",
    ]

    for i, r in enumerate(results, start=1):
        result_cell = "✅ PASS" if r.passed else "❌ FAIL"
        # Escape pipe characters in notes so the table stays valid.
        notes = r.notes.replace("|", "\\|")
        lines.append(
            f"| {i} | {r.meta.label} | {r.meta.layer} "
            f"| {result_cell} | {r.duration_seconds:.3f} | {notes} |"
        )

    lines += [""]

    # ── Failure details ──────────────────────────────────────────────────────
    failures = [r for r in results if not r.passed and r.error_excerpt]
    if failures:
        lines += ["## Failure Details", ""]
        for r in failures:
            lines += [
                f"### {r.meta.label}",
                "",
                f"**Layer:** {r.meta.layer}  ",
                "",
                "```",
                r.error_excerpt,
                "```",
                "",
            ]

    # ── Evaluation layer legend ──────────────────────────────────────────────
    lines += [
        "## Evaluation Layer Legend",
        "",
        "| Layer | What it checks |",
        "|-------|----------------|",
        "| Trace + full pipeline | End-to-end run produces the right shape of output |",
        "| Failure-handling | Partial failures are surfaced gracefully, never crash |",
        "| Governance / output | Uncited claims are dropped before they reach the user |",
        "| Trace / reliability | Per-run resource caps are enforced deterministically |",
        "| Adversarial / governance | Sensational low-credibility claims are hedged |",
        "",
        "---",
        "_Generated by `eval/run_eval.py`_",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the competitive-intel eval suite.")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Pass -v to pytest for verbose per-test output.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Override the output path for eval_report.md.",
    )
    args = parser.parse_args()

    extra = ["-v"] if args.verbose else []
    sys.exit(run_eval(report_path=args.report, extra_pytest_args=extra))
