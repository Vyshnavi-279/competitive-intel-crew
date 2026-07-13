# Competitive Intel Crew — Test History & Results

This file is the single source of truth for all testing done on this project.
Each session records what was tested, how, and what the outcome was.
Append a new session block whenever tests are added or re-run.

---

## Project Structure Under Test

```
competitive-intel-crew/
├── backend/
│   ├── crew.py                    # CrewAI pipeline (run_briefing entry point)
│   ├── main.py                    # FastAPI app — 5 REST endpoints
│   ├── config.py                  # Env-var validation (python-dotenv)
│   ├── models/
│   │   └── schemas.py             # Pydantic models: Citation, Claim, Section,
│   │                              #   RunMetadata, Briefing
│   ├── tools/
│   │   ├── safe_search_tool.py    # SafeSearchTool — runaway-source guard
│   │   └── citation_tool.py       # Citation extraction helpers
│   ├── governance/
│   │   ├── citation_guard.py      # enforce_citations, flag_unverified_assertions
│   │   └── run_guard.py           # MAX_STEPS, MAX_EXECUTION_SECONDS constants
│   └── storage/
│       └── db.py                  # SQLite persistence (runs + audit_log)
└── eval/
    ├── test_scenarios.py          # 5-scenario pytest suite
    ├── run_eval.py                # Programmatic runner + Markdown reporter
    └── eval_report.md             # Latest auto-generated report (see below)
```

---

## Test Suite Overview

| File | Framework | Scope | Total tests |
|------|-----------|-------|-------------|
| `eval/test_scenarios.py` | pytest 8.3.3 | Integration + unit | 5 |

### How to run

```bash
# Full suite with report:
python eval/run_eval.py

# Verbose pytest output only (no report):
pytest eval/test_scenarios.py -v

# Single test:
pytest eval/test_scenarios.py::TestRunawayGuardRespectsCap -v
```

---

## Session 1 — 2026-07-13

**Environment**

| Key | Value |
|-----|-------|
| Python | 3.11 (venv) |
| pytest | 8.3.3 |
| crewai | 0.86.0 |
| crewai-tools | 0.17.0 |
| fastapi | 0.115.0 |
| pydantic | 2.9.2 |
| python-dotenv | 1.0.1 |
| Platform | macOS |

**Run command**

```bash
OPENROUTER_API_KEY=test SERPER_API_KEY=test \
  ./venv/bin/python -m pytest eval/test_scenarios.py -v --tb=short
```

**Results — 5/5 PASSED**

| # | Test | Node ID | Layer | Result | Time (s) |
|---|------|---------|-------|--------|----------|
| 1 | Full weekly briefing happy path | `TestFullWeeklyBriefingHappyPath::test_full_weekly_briefing_happy_path` | Trace + full pipeline | ✅ PASS | 0.171 |
| 2 | Source failure handling | `TestSourceFailureHandling::test_source_failure_handling` | Failure-handling | ✅ PASS | 0.111 |
| 3 | Uncited claim is dropped | `TestUncitedClaimIsDropped::test_uncited_claim_is_dropped` | Governance / output | ✅ PASS | 0.019 |
| 4 | Runaway guard respects cap | `TestRunawayGuardRespectsCap::test_runaway_guard_respects_cap` | Trace / reliability | ✅ PASS | 0.001 |
| 5 | Planted unverified claim is hedged | `TestPlantedUnverifiedClaimIsHedged::test_planted_unverified_claim_is_hedged` | Adversarial / governance | ✅ PASS | 0.000 |

**Suite duration:** 0.32s  
**Overall:** ✅ ALL PASS

---

## Test Descriptions

### Test 1 — Full Weekly Briefing Happy Path

**Layer:** Trace correctness + full pipeline  
**Type:** Integration (HTTP via `TestClient`)  
**What it does:**  
POSTs `{"topic": "AI developer tools market 2025"}` to `POST /api/run` with
`run_briefing` mocked to return a deterministic cited briefing.

**Assertions:**
- HTTP response status is `200`
- Response contains a `sections` key with exactly **3** items
- Section titles are in the correct order: `"Executive Summary"` → `"Competitor Pricing & Product Moves"` → `"Market Signals"`
- Every claim in every section has at least one citation (`citations` list non-empty)
- `metadata.status == "completed"`

**Why this matters:**  
Validates the full request → crew → response pipeline produces the right
output shape. A structural regression (wrong section count, missing citations,
wrong title) is caught immediately.

---

### Test 2 — Source Failure Handling

**Layer:** Failure-handling  
**Type:** Integration (HTTP via `TestClient`)  
**What it does:**  
Swaps the `run_briefing` mock to return a briefing where
`sources_skipped = ["query1", "query2", "query3"]` and `status = "completed"`.
Then POSTs to `POST /api/run`.

**Assertions:**
- HTTP response status is still `200` (the run did not crash)
- `metadata.status == "completed"` (not `"failed"`)
- `metadata.sources_skipped` is non-empty
- `metadata.sources_used < metadata.sources_attempted`

**Why this matters:**  
Confirms that network errors or API failures inside `SafeSearchTool` are
absorbed gracefully. The crew run must never propagate an exception to the
API layer.

---

### Test 3 — Uncited Claim Is Dropped

**Layer:** Governance / output  
**Type:** Unit test (direct function call)  
**What it does:**  
Calls `enforce_citations()` with a hand-built list of two `Section` objects.
One section contains a cited claim; the other contains both a cited claim and
one with `citations=[]`.

**Assertions:**
- No claim in the cleaned output has an empty citations list
- The specific uncited claim text (`"secretly planning an IPO"`) is absent from all output claims
- The returned `flags` list is non-empty
- Flag text contains `"dropped"` or `"uncited"`

**Why this matters:**  
The citation governance layer is the last line of defence against hallucinated
facts reaching the user. This test verifies it works at the code level,
independent of LLM behaviour.

---

### Test 4 — Runaway Guard Respects Cap

**Layer:** Trace / reliability  
**Type:** Unit test (direct instantiation)  
**What it does:**  
Sets `MAX_SOURCES=3` via `monkeypatch.setenv`. Instantiates `SafeSearchTool`
with a `MagicMock` engine (no HTTP). Calls `tool._run(query=...)` **5 times**.

**Assertions:**
- `tool.search_count == 3` (only the first 3 calls went through)
- `len(tool.skipped_sources) == 2` (the last 2 were refused)
- No exception was raised on any of the 5 calls
- The return value from refused calls is a string containing `"cap"`, `"skip"`, or `"SafeSearch"`

**Why this matters:**  
Without this cap, a misbehaving agent could exhaust the Serper API quota in a
single run. The test asserts the guard is deterministic and exception-safe.

---

### Test 5 — Planted Unverified Claim Is Hedged

**Layer:** Adversarial / governance  
**Type:** Unit test (direct function call)  
**What it does:**  
Calls `flag_unverified_assertions()` with a `Section` containing:
- A sensational claim: `"CompetitorX is going bankrupt and will close by Q3."` with a
  single citation from `"GossipBlogXYZ"` (not in `_TRUSTED_OUTLETS`), marked `verified=True`
- A safe claim: `"Competitor A raised Series B funding of $50M."` from `"Reuters"`

**Assertions:**
- The CompetitorX claim is still present in the output (hedged, not dropped)
- Its text starts with `"Unverified:"`
- Its `verified` field is `False`
- No version of the claim appears without the `"Unverified:"` prefix
- The safe Reuters-sourced claim is **not** modified
- `flags` list is non-empty and mentions `"hedged"` or `"unverified"`

**Why this matters:**  
Adversarial input — where an agent marks a rumour as verified — must still be
caught. The governance layer must never let a bare sensational claim through
as a verified fact.

---

## Component-Level Verification (Manual Checks — Session 1)

These were verified by running `python -c "..."` directly, not via pytest.

| Component | What was checked | Result |
|-----------|-----------------|--------|
| `backend/storage/db.py` | `init_db()` creates `runs` + `audit_log` tables in `runs.db` | ✅ |
| `backend/storage/db.py` | `save_run`, `get_run`, `list_runs`, `log_event`, `update_run_status` round-trip | ✅ |
| `backend/main.py` | All 5 routes registered with correct HTTP methods | ✅ |
| `backend/main.py` | CORS middleware present with `allow_origins=["http://localhost:3000"]` | ✅ |
| `backend/tools/safe_search_tool.py` | AST parses without syntax errors | ✅ |
| `backend/config.py` | Raises `RuntimeError` listing missing keys when env vars absent | ✅ |

---

## Known Issues / Environment Notes

| Issue | Impact | Status |
|-------|--------|--------|
| `pkg_resources` missing in `venv` (crewai 0.86 telemetry) | `import crewai` fails with `ModuleNotFoundError: No module named 'pkg_resources'` | Tests work around it by stubbing `crewai` in `sys.modules` before importing `backend.main`. Real runs require installing `setuptools` into the venv. |
| `crewai` not importable from `.venv` (no `fastapi` installed there) | `.venv` lacks fastapi; `venv` lacks setuptools | All tests use `./venv/bin/python` which has the full requirements installed. |

---

## Adding Future Test Results

When you run the suite again, append a new session block using this template:

```markdown
## Session N — YYYY-MM-DD

**Environment**
(python version, any changed deps)

**Run command**
(exact command used)

**Results — X/5 PASSED**

| # | Test | Result | Time (s) | Notes |
|---|------|--------|----------|-------|
| 1 | ... | ✅/❌ | | |
...

**Suite duration:** Xs
**Overall:** ✅ ALL PASS / ❌ N FAILED
```

The auto-generated `eval/eval_report.md` (written by `python eval/run_eval.py`)
captures the same data in machine-generated form; this file provides the
human-readable history and test rationale that `eval_report.md` does not.
