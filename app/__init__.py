"""
app - Interactive Scenario Game Server

텍스트 기반 인터랙티브 시나리오 게임 서버 패키지
"""
from app.loader import ScenarioAssets, ScenarioLoader, load_scenario_assets
from app.models import (
    Intent,
    NightResult,
    NPCState,
    ParsedInput,
    StateDelta,
    StepRequest,
    StepResponse,
    ToolCall,
    ToolName,
    ToolResult,
    WorldState,
)
from app.agents.generative_night import NightController, get_night_controller
from app.state import WorldStateManager

__version__ = "0.1.0"

__all__ = [
    # Loader
    "ScenarioAssets",
    "ScenarioLoader",
    "load_scenario_assets",
    # Models
    "Intent",
    "ParsedInput",
    "WorldState",
    "NPCState",
    "ToolCall",
    "ToolName",
    "ToolResult",
    "NightResult",
    "StateDelta",
    "StepRequest",
    "StepResponse",
    # Night
    "NightController",
    "get_night_controller",
    # State
    "WorldStateManager",
]
