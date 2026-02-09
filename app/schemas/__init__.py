"""
app/schemas/__init__.py
스키마 통합 export

모든 스키마를 이 모듈에서 import 할 수 있습니다:
    from app.schemas import NpcSchema, WorldState, Intent, ...
"""

# ── Core (Enums, NPC, Player, Item) ──────────────────────
from app.schemas.core import (
    NPCStatus,
    Intent,
    ToolName,
    NpcSchema,
    NpcCollectionSchema,
    PlayerSchema,
    PlayerMemoSchema,
    ItemSchema,
    ItemsCollectionSchema,
)

# ── State (GameState, Memory, WorldData) ─────────────────
from app.schemas.state import (
    MemoryEntrySchema,
    MemoryStreamSchema,
    MEMORY_OBSERVATION,
    MEMORY_REFLECTION,
    MEMORY_PLAN,
    MEMORY_DIALOGUE,
    MAX_MEMORIES_PER_NPC,
    NPCState,
    WorldState,
    StateDelta,
    merge_deltas,
    CurrentStateSchema,
    LockSchema,
    LocksSchemaList,
    StoryNodeSchema,
    StoryGraphSchema,
    EndingSchema,
    ScenarioSchema,
    WorldDataSchema,
)

# ── IO (Tool, Night, LLM, API, ClientSync) ───────────────
from app.schemas.io import (
    ToolCall,
    ToolResult,
    NightResult,
    UserInputSchema,
    WorldInfoSchema,
    LogicContextSchema,
    ModelConfigSchema,
    LLMInputPayload,
    LLMResponseSchema,
    StepRequest,
    StepResponse,
    GameClientSyncSchema,
)


__all__ = [
    # Core
    "NPCStatus", "Intent", "ToolName",
    "NpcSchema", "NpcCollectionSchema",
    "PlayerSchema", "PlayerMemoSchema",
    "ItemSchema", "ItemsCollectionSchema",
    # State
    "MemoryEntrySchema", "MemoryStreamSchema",
    "MEMORY_OBSERVATION", "MEMORY_REFLECTION", "MEMORY_PLAN", "MEMORY_DIALOGUE",
    "MAX_MEMORIES_PER_NPC",
    "NPCState", "WorldState", "StateDelta", "merge_deltas",
    "CurrentStateSchema", "LockSchema", "LocksSchemaList",
    "StoryNodeSchema", "StoryGraphSchema",
    "EndingSchema", "ScenarioSchema", "WorldDataSchema",
    # IO
    "ToolCall", "ToolResult", "NightResult",
    "UserInputSchema", "WorldInfoSchema", "LogicContextSchema",
    "ModelConfigSchema", "LLMInputPayload",
    "LLMResponseSchema",
    "StepRequest", "StepResponse",
    "GameClientSyncSchema",
]
