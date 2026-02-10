"""
app/schemas/__init__.py
모든 스키마 모듈을 통합 export
"""

# Enums
from app.schemas.status import (
    NPCStatus,
    Intent,
    ToolName,
    NpcId,
    GameStatus,
    ChatAt,
)

# NPC
from app.schemas.npc_info import (
    NpcSchema,
    NpcCollectionSchema,
)

# Game State (Runtime)
from app.schemas.game_state import (
    NPCState,
    WorldState,
    StateDelta,
    merge_deltas,
)

# Player
from app.schemas.player_info import (
    PlayerMemoSchema,
    PlayerSchema,
)

# Item
from app.schemas.item_info import (
    ItemSchema,
    ItemsCollectionSchema,
)

# Tool
from app.schemas.tool import (
    ToolCall,
    ToolResult,
)

# Request/Response
from app.schemas.request_response import (
    UserInputSchema,
    StepRequest,
    StepResponse,
    TurnResult,
    StepRequestSchema,
    NightRequestBody,
    NightTurnResult,
    ScenarioInfoResponse,
    StateResponse,
    GameResponse,
)

# Memory
from app.schemas.memory import (
    MemoryEntrySchema,
    MemoryStreamSchema,
    MEMORY_OBSERVATION,
    MEMORY_REFLECTION,
    MEMORY_PLAN,
    MEMORY_DIALOGUE,
    MAX_MEMORIES_PER_NPC,
)

# Night
from app.schemas.night import (
    NightResult,
    NightExposedLog,
    FullLogRef,
    PlayerEffect,
    NpcDelta,
    NightEffects,
    UiData,
    NightLogResponse,
)

# Client Sync
from app.schemas.client_sync import (
    GameClientSyncSchema,
)

# World Data (Static)
from app.schemas.world_meta_data import (
    CurrentStateSchema,
    LockSchema,
    LocksSchemaList,
    StoryNodeSchema,
    StoryGraphSchema,
    EndingSchema,
    ScenarioSchema,
    WorldDataSchema,
)

# Ending / Lock / Condition
from app.schemas.ending import (
    EndingInfo,
    EndingCheckResult,
)

from app.schemas.lock import (
    UnlockedInfo,
    LockCheckResult,
)

from app.schemas.condition import (
    EvalContext,
)

# LLM Parsed Response
from app.schemas.llm_parsed_response import (
    LLMParsedResponse,
)

__all__ = [
    # Enums
    "NPCStatus", "Intent", "ToolName", "NpcId", "GameStatus", "ChatAt",
    # NPC
    "NpcSchema", "NpcCollectionSchema",
    # Game State
    "NPCState", "WorldState", "StateDelta", "merge_deltas",
    # Player
    "PlayerMemoSchema", "PlayerSchema",
    # Item
    "ItemSchema", "ItemsCollectionSchema",
    # Tool
    "ToolCall", "ToolResult",
    # Request/Response
    "UserInputSchema", "StepRequest", "StepResponse", "TurnResult",
    "StepRequestSchema", "NightRequestBody", "NightTurnResult",
    "ScenarioInfoResponse", "StateResponse", "GameResponse",
    # Memory
    "MemoryEntrySchema", "MemoryStreamSchema",
    "MEMORY_OBSERVATION", "MEMORY_REFLECTION", "MEMORY_PLAN", "MEMORY_DIALOGUE",
    "MAX_MEMORIES_PER_NPC",
    # Night
    "NightResult", "NightExposedLog", "FullLogRef",
    "PlayerEffect", "NpcDelta", "NightEffects", "UiData", "NightLogResponse",
    # Client Sync
    "GameClientSyncSchema",
    # World Data
    "CurrentStateSchema", "LockSchema", "LocksSchemaList",
    "StoryNodeSchema", "StoryGraphSchema", "EndingSchema",
    "ScenarioSchema", "WorldDataSchema",
    # Ending / Lock / Condition
    "EndingInfo", "EndingCheckResult",
    "UnlockedInfo", "LockCheckResult",
    "EvalContext",
    # LLM
    "LLMParsedResponse",
]
