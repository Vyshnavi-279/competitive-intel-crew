"""
RunGuard — constants that bound a crew execution.

WHY THIS GUARDRAIL EXISTS:
Without hard limits, a CrewAI crew with many agents and tasks can loop
indefinitely, consuming unbounded LLM tokens and wall-clock time.  These
constants are read from environment variables (with sensible defaults) and
used when configuring the crew so that `max_iter` and `max_execution_time`
are enforced at the framework level.
"""

import os

# Maximum number of reasoning iterations each agent is allowed.
# Read from env so it can be tuned per environment (dev / prod / batch).
MAX_STEPS: int = int(os.getenv("MAX_STEPS", "25"))

# Maximum wall-clock seconds the entire crew run may take.
# CrewAI's max_execution_time is specified in seconds.
MAX_EXECUTION_SECONDS: int = int(os.getenv("MAX_EXECUTION_SECONDS", "600"))