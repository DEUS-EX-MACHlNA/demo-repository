"""스키마 통합 테스트"""
import sys
sys.path.insert(0, '.')

# Core
from app.schemas.core import (
    NPCStatus, Intent, ToolName,
    NpcSchema, PlayerSchema, ItemSchema
)

# State
from app.schemas.state import (
    WorldState, NPCState, StateDelta,
    MemoryEntrySchema, LockSchema
)

# IO
from app.schemas.io import (
    UserInputSchema, ToolResult, NightResult,
    LLMResponseSchema, StepRequest
)

print("=" * 60)
print("스키마 통합 테스트")
print("=" * 60)

# 1. Core 테스트
print("\n[1] Core 스키마:")
print(f"  - NPCStatus: {list(NPCStatus)}")
print(f"  - Intent: {list(Intent)}")
print(f"  - ToolName: {list(ToolName)}")

# 2. State 테스트
print("\n[2] State 스키마:")
world = WorldState(
    turn=1,
    npcs={"test": NPCState(npc_id="test", stats={"trust": 50})},
    vars={"humanity": 100}
)
print(f"  - WorldState created: turn={world.turn}, npcs={len(world.npcs)}")

# 3. IO 테스트
print("\n[3] IO 스키마:")
user_input = UserInputSchema(
    chat_input="안녕",
    npc_name="brother"
)
combined = user_input.to_combined_string()
print(f"  - UserInputSchema: '{combined}'")

tool_result = ToolResult(
    state_delta={},
    event_description=["test event"]
)
print(f"  - ToolResult created: {len(tool_result.event_description)} events")

print("\n" + "=" * 60)
print("✅ 모든 스키마 import 및 생성 성공!")
print("=" * 60)
