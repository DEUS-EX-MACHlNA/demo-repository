"""
app/schemas/request_response.py
API 요청/응답 스키마 통합
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# ============================================================
# Step 요청/응답 (game 라우터용)
# ============================================================
class StepRequestSchema(BaseModel):
    """게임 대화 요청 (game 라우터)"""
    chat_input: str
    npc_name: Optional[str] = None
    item_name: Optional[str] = None

    def to_combined_string(self) -> str:
        """입력 컨텍스트(NPC, 아이템)를 포함한 문자열 반환"""
        parts = []
        if self.npc_name:
            parts.append(f"(target: {self.npc_name})")
        if self.item_name:
            parts.append(f"(use: {self.item_name})")
        
        parts.append(self.chat_input)
        return " ".join(parts)

class StepResponseSchema(BaseModel):
    """낮 파이프라인 실행 결과"""
    narrative: str
    ending_info: Optional[Dict[str, Any]] = None
    # 이 부분은 나중에 아이템 상태를 부르거나 npc의 상태를 추가로 넣으면 되겠지
    state_result: Dict[str, Any] = Field(default_factory=dict) # Renamed to result
    debug: Dict[str, Any] = Field(default_factory=dict)

# ============================================================
# Night 요청/응답
# ============================================================
class NightRequestBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/night 요청 바디"""
    user_id: str
# class NightResponse(BaseModel):
#     """밤 파이프라인 실행 결과"""
#     narrative: str
#     ending_info: Optional[Dict[str, Any]] = None
#     world_state: Dict[str, Any] = Field(default_factory=dict)
#     debug: Dict[str, Any] = Field(default_factory=dict)

class NightDialogue(BaseModel):
    speaker_name: str = Field(..., description="화자 이름 (예: 엘리노어 (새엄마))")
    dialogue: str = Field(..., description="대사 내용")

class NightResponseResult(BaseModel):
    narrative: str = Field(..., description="별도의 요청 없이 표시될 밤 이야기 개요")
    dialogues: List[NightDialogue] = Field(..., description="밤 대화 리스트")
    npc_state_results: Dict[str, Dict[str, int]] = Field(..., description="NPC 상태 결과 (Key: NPC ID, Value: {stat_name: value})")
    ending_info: Optional[Dict[str, Any]] = None
    vars: Optional[Dict[str, Any]]

# ============================================================
# 시나리오 정보 응답
# ============================================================
class ScenarioInfoResponse(BaseModel):
    """시나리오 정보 응답"""
    scenario_id: str
    title: str
    genre: str
    turn_limit: int
    npcs: List[str]
    items: List[str]


# ============================================================
# 상태 조회 응답
# ============================================================
class StateResponse(BaseModel):
    """상태 조회 응답"""
    user_id: str
    scenario_id: str
    state: Dict[str, Any]


# ============================================================
# 게임 응답 (scenario 라우터용)
# ============================================================
class GameResponse(BaseModel):
    """게임 응답 (DB 조회용)"""
    id: int
    user_id: int
    scenarios_id: int
    world_state: Optional[Dict[str, Any]] = None
    player_state: Optional[Dict[str, Any]] = None
    npc_state: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
