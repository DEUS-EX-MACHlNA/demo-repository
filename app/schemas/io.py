"""
app/schemas/io.py
입출력 스키마 (Tool, Night, LLM, API, ClientSync)
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.core import NpcCollectionSchema, PlayerSchema, ItemsCollectionSchema
from app.schemas.state import WorldDataSchema


# ============================================================
# Tool
# ============================================================
class ToolCall(BaseModel):
    """Controller가 결정한 Tool 호출 사양"""
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Tool 실행 결과"""
    state_delta: Dict[str, Any]
    event_description: List[str]


# ============================================================
# Night Phase
# ============================================================
class NightResult(BaseModel):
    """NightController 실행 결과

    NPC 3명이 함께 나누는 그룹 대화를 담아 반환.
    """
    night_delta: Dict[str, Any]
    night_conversation: List[Dict[str, str]]


# ============================================================
# LLM Payload
# ============================================================
class UserInputSchema(BaseModel):
    """유저 입력"""
    chat_input: str
    npc_name: Optional[str] = None
    item_name: Optional[str] = None

    def to_combined_string(self) -> str:
        """
        UserInputSchema를 단일 문자열로 변환합니다.

        chat_input에 npc_name, item_name 정보를 자연스럽게 결합합니다.

        Returns:
            결합된 문자열
        """
        parts = [self.chat_input]

        if self.npc_name:
            parts.append(f"(대상 NPC: {self.npc_name})")

        if self.item_name:
            parts.append(f"(대상 아이템: {self.item_name})")

        return " ".join(parts)


class WorldInfoSchema(BaseModel):
    """월드 정보 (LLM에 전달)"""
    player: PlayerSchema
    npcs: NpcCollectionSchema
    items: ItemsCollectionSchema


class LogicContextSchema(BaseModel):
    """로직 컨텍스트"""
    meta: Dict[str, Any]
    state: Dict[str, Any]
    rules: Dict[str, Any]


class ModelConfigSchema(BaseModel):
    """모델 설정"""
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    extra_settings: Dict[str, Any] = Field(default_factory=dict)


class LLMInputPayload(BaseModel):
    """최종 LLM 페이로드"""
    arg1_user_input: UserInputSchema
    arg2_world_info: WorldInfoSchema
    arg3_logic_context: LogicContextSchema
    arg4_model_config: ModelConfigSchema


# ============================================================
# LLM Response
# ============================================================
class LLMResponseSchema(BaseModel):
    """LLM 응답"""
    response_text: str

    update_vars: Dict[str, Any] = {}
    update_flags: Dict[str, Any] = {}

    items_to_add: List[str] = []
    items_to_remove: List[str] = []

    new_memo: Optional[str] = None
    update_memory: Dict[str, Any] = {}

    next_node: Optional[str] = None


# ============================================================
# API Request/Response
# ============================================================
class StepRequest(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 요청 바디"""
    user_id: str
    text: str


class StepResponse(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 응답"""
    dialogue: str
    is_observed: bool
    debug: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Client Sync
# ============================================================
class GameClientSyncSchema(BaseModel):
    """클라이언트 동기화 스키마"""
    world: WorldDataSchema = Field(..., description="정적 세계 데이터 및 현재 월드 상태 (시나리오, 맵, 턴 등)")
    player: PlayerSchema = Field(..., description="플레이어의 개인 상태 (인벤토리, 메모, 위치)")
    npcs: NpcCollectionSchema = Field(..., description="모든 NPC의 상태 정보")
