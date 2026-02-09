"""스키마만 직접 import 테스트 (app/__init__.py 우회)"""
import sys
from pathlib import Path

# app 폴더를 sys.path에 추가
app_path = Path(__file__).parent / "app"
sys.path.insert(0, str(app_path))

# 직접 import
from schemas.core import (
    NPCStatus, Intent, ToolName,
    NpcSchema, PlayerSchema, ItemSchema
)

from schemas.state import (
    WorldState, NPCState, StateDelta,
    MemoryEntrySchema, LockSchema
)

from schemas.io import (
    UserInputSchema, ToolResult, NightResult,
    LLMResponseSchema, StepRequest
)

print("=" * 60)
print("스키마 통합 테스트 (app/__init__.py 우회)")
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
print(f"  - WorldState: turn={world.turn}, npcs={len(world.npcs)}, vars={world.vars}")

delta = StateDelta(
    vars={"humanity": -10},
    npc_stats={"test": {"trust": 5}}
)
print(f"  - StateDelta: vars={delta.vars}, npc_stats={delta.npc_stats}")

# 3. IO 테스트
print("\n[3] IO 스키마:")
user_input = UserInputSchema(
    chat_input="안녕",
    npc_name="brother"
)
combined = user_input.to_combined_string()
print(f"  - UserInputSchema: '{combined}'")

user_input2 = UserInputSchema(
    chat_input="열쇠를 사용한다",
    item_name="silver_key"
)
combined2 = user_input2.to_combined_string()
print(f"  - UserInputSchema (with item): '{combined2}'")

tool_result = ToolResult(
    state_delta={"vars": {"test": 1}},
    event_description=["테스트 이벤트 발생"]
)
print(f"  - ToolResult: {len(tool_result.event_description)} events")

llm_response = LLMResponseSchema(
    response_text="안녕하세요!",
    update_vars={"test": 5},
    items_to_add=["new_item"]
)
print(f"  - LLMResponseSchema: response_text='{llm_response.response_text[:20]}...', vars={llm_response.update_vars}")

print("\n" + "=" * 60)
print("✅ 모든 스키마 import 및 생성 성공!")
print("=" * 60)
print("\n통합된 파일 구조:")
print("  - core.py: Enums, NPC, Player, Item")
print("  - state.py: Memory, GameState, WorldData")
print("  - io.py: Tool, Night, LLM, API, ClientSync")
