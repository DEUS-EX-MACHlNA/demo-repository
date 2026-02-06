"""
app/schemas/__init__.py
스키마 통합 export

모든 스키마를 이 모듈에서 import 할 수 있습니다:
    from app.schemas import NpcSchema, WorldState, Intent, ...
"""

# ── Enums ─────────────────────────────────────────────────────
from app.schemas.enums import (
    NPCStatus,
    Intent,
    ToolName,
)

# ── NPC ───────────────────────────────────────────────────────
from app.schemas.npc import (
    NpcSchema,
    NpcCollectionSchema,
)

# ── Player ────────────────────────────────────────────────────
from app.schemas.player import (
    PlayerSchema,
    PlayerMemoSchema,
)

# ── Item ──────────────────────────────────────────────────────
from app.schemas.item import (
    ItemSchema,
    ItemsCollectionSchema,
)

# ── Memory ────────────────────────────────────────────────────
from app.schemas.memory import (
    MemoryEntrySchema,
    MemoryStreamSchema,
    MEMORY_OBSERVATION,
    MEMORY_REFLECTION,
    MEMORY_PLAN,
    MEMORY_DIALOGUE,
    MAX_MEMORIES_PER_NPC,
)

# ── World Data (정적 시나리오 구조) ────────────────────────────
from app.schemas.world_data import (
    CurrentStateSchema,
    LockSchema,
    LocksSchemaList,
    StoryNodeSchema,
    StoryGraphSchema,
    EndingSchema,
    ScenarioSchema,
    WorldDataSchema,
)

# ── Game State (런타임 상태) ──────────────────────────────────
from app.schemas.game_state import (
    NPCState,
    WorldState,
    StateDelta,
    merge_deltas,
)

# ── Tool ──────────────────────────────────────────────────────
from app.schemas.tool import (
    ToolCall,
    ToolResult,
)

# ── Parser ────────────────────────────────────────────────────
from app.schemas.parser import (
    ParsedInput,
)

# ── Night ─────────────────────────────────────────────────────
from app.schemas.night import (
    NightResult,
)

# ── Request/Response (API) ────────────────────────────────────
from app.schemas.request_response import (
    StepRequest,
    StepResponse,
)

# ── LLM Payload ──────────────────────────────────────────────
from app.schemas.llm_payload import (
    UserInputSchema,
    WorldInfoSchema,
    LogicContextSchema,
    ModelConfigSchema,
    LLMInputPayload,
)

# ── LLM Response ─────────────────────────────────────────────
from app.schemas.llm_response import (
    LLMResponseSchema,
)

# ── Client Sync ──────────────────────────────────────────────
from app.schemas.client_sync import (
    GameClientSyncSchema,
)


__all__ = [
    # Enums
    "NPCStatus",
    "Intent",
    "ToolName",
    # NPC
    "NpcSchema",
    "NpcCollectionSchema",
    # Player
    "PlayerSchema",
    "PlayerMemoSchema",
    # Item
    "ItemSchema",
    "ItemsCollectionSchema",
    # Memory
    "MemoryEntrySchema",
    "MemoryStreamSchema",
    "MEMORY_OBSERVATION",
    "MEMORY_REFLECTION",
    "MEMORY_PLAN",
    "MEMORY_DIALOGUE",
    "MAX_MEMORIES_PER_NPC",
    # World Data
    "CurrentStateSchema",
    "LockSchema",
    "LocksSchemaList",
    "StoryNodeSchema",
    "StoryGraphSchema",
    "EndingSchema",
    "ScenarioSchema",
    "WorldDataSchema",
    # Game State
    "NPCState",
    "WorldState",
    "StateDelta",
    "merge_deltas",
    # Tool
    "ToolCall",
    "ToolResult",
    # Parser
    "ParsedInput",
    # Night
    "NightResult",
    # Request/Response
    "StepRequest",
    "StepResponse",
    # LLM Payload
    "UserInputSchema",
    "WorldInfoSchema",
    "LogicContextSchema",
    "ModelConfigSchema",
    "LLMInputPayload",
    # LLM Response
    "LLMResponseSchema",
    # Client Sync
    "GameClientSyncSchema",
]
