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

# Read from the centralised Settings object so that .env is guaranteed to be
# loaded before these values are evaluated (config.py calls load_dotenv at
# import time, before any other backend module uses these constants).
from backend.config import settings

# Maximum number of reasoning iterations each agent is allowed.
MAX_STEPS: int = settings.max_steps

# Maximum wall-clock seconds the entire crew run may take.
# Not part of the Settings dataclass (rarely needs tuning), so read directly.
MAX_EXECUTION_SECONDS: int = int(os.getenv("MAX_EXECUTION_SECONDS", "600"))
