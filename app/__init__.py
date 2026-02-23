"""
app - Interactive Scenario Game Server

텍스트 기반 인터랙티브 시나리오 게임 서버 패키지
"""
from app.loader import ScenarioAssets, ScenarioLoader, load_scenario_assets
from app.schemas import (
    Intent,
    NightResult,
    NPCState,
    StateDelta,
    ToolCall,
    ToolName,
    ToolResult,
    WorldStatePipeline,
)
from app.day_controller import DayController, get_day_controller
from app.night_controller import NightController, get_night_controller
# from app.state import WorldStateManager

__version__ = "0.1.0"

__all__ = [
    # Loader
    "ScenarioAssets",
    "ScenarioLoader",
    "load_scenario_assets",
    # Models
    "Intent",
    # "ParsedInput",
    "WorldStatePipeline",
    "NPCState",
    "ToolCall",
    "ToolName",
    "ToolResult",
    "NightResult",
    "StateDelta",
    "StepRequest",
    "StepResponse",
    # Controllers
    "DayController",
    "get_day_controller",
    "NightController",
    "get_night_controller",
    # State
    "WorldStateManager",
]
