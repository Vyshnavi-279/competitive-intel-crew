# MarketPulse — Competitive Intelligence Crew

A multi-agent AI system that researches, analyses, and publishes weekly competitive-intelligence briefings for strategy and product teams.

---

## Business Problem

Keeping up with competitor pricing moves, product launches, and market signals requires someone to manually trawl dozens of sources every week — work that is time-consuming, inconsistently done, and easy to deprioritise under deadline pressure. MarketPulse automates this with a four-agent CrewAI crew that searches the live web, extracts structured claims, enforces citation quality programmatically, and routes the finished briefing through a human review gate before it reaches the sales and strategy org. The result is a traceable, sourced report that a VP Strategy can act on with confidence.

---

## Architecture

```
User / Scheduler
      │
      ▼
 Coordinator agent   ← plans sections and hands off
      │
      ▼
 Researcher agent    ← web search via SafeSearchTool (Serper API, capped at MAX_SOURCES)
      │
      ▼
 Analyst agent       ← extracts and classifies claims, notes confidence
      │
      ▼
 Writer agent        ← produces the final markdown briefing with inline citations
      │
      ▼
 Governance layer    ← enforce_citations drops uncited claims
                        flag_unverified_assertions hedges sensational single-source claims
                        RunGuard caps steps and wall-clock time
      │
      ▼
 Human review gate   ← status = pending_review; reviewer Approves or Rejects in the UI
      │
      ▼
 Published briefing  ← status = published; stored in SQLite, surfaced in dashboard
```

**Stack**

| Layer | Technology |
|-------|-----------|
| Agent framework | CrewAI 0.86 |
| LLM | OpenRouter (Claude 3.5 Sonnet by default) |
| Web search | Serper API via `SafeSearchTool` |
| Backend API | FastAPI + uvicorn |
| Storage | SQLite (stdlib `sqlite3`, no ORM) |
| Scheduled runs | APScheduler `BackgroundScheduler` |
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind |
| Evaluation | pytest + FastAPI `TestClient` |

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Serper API key](https://serper.dev) and an [OpenRouter API key](https://openrouter.ai)

### 1 — Clone and create the Python environment

```bash
git clone <repo-url>
cd competitive-intel-crew
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```
OPENROUTER_API_KEY=sk-or-...
SERPER_API_KEY=...
MODEL_NAME=openrouter/anthropic/claude-3.5-sonnet   # or any OpenRouter model
MAX_SOURCES=15
MAX_STEPS=25
```

Optional — standing topics for the weekly scheduler:

```
STANDING_TOPICS=AI developer tools market,Cloud infrastructure pricing
```

### 3 — Start the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

The API is now available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 4 — Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard available at `http://localhost:3000`.

---

## Running the Evaluation Suite

```bash
# From the project root (venv active):
pytest eval/test_scenarios.py -v
```

Or via the full harness (runs pytest and writes `eval/eval_report.md`):

```bash
python eval/run_eval.py
```

The five test scenarios cover: full pipeline trace, partial source-failure handling, citation governance, runaway-source cap, and adversarial claim hedging.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/run` | Kick off a new briefing run |
| `GET` | `/api/runs` | List recent run summaries |
| `GET` | `/api/runs/{id}` | Full briefing JSON for one run |
| `POST` | `/api/runs/{id}/publish` | Approve a pending-review briefing |
| `POST` | `/api/runs/{id}/reject` | Reject with optional reason |
| `GET` | `/api/health` | Liveness probe |

---

## Stretch Features

- **Fact-checker agent** — a dedicated fifth agent that cross-checks the Writer's claims against the raw research before the briefing reaches the governance layer.
- **Human review gate** — every completed briefing lands in `pending_review`; a reviewer must explicitly approve (publish) or reject it via the dashboard before it reaches the broader org.
- **Scheduled weekly runs** — APScheduler fires `run_briefing()` every Monday at 08:00 for a configurable list of standing topics (`STANDING_TOPICS` env var), with audit-log entries distinguishing automated runs (`triggered_by: scheduled`) from manual ones.

- # Competitive Intelligence Crew (MarketPulse)

## 🚀 Live Deployments
* **Frontend Dashboard (Netlify):** 
* **Backend API Gateway (Render):** *Running live on Render cluster*
