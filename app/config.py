import os
from pathlib import Path

SCENARIOS_BASE_PATH = Path(__file__).parent.parent / "scenarios"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")