"""
app/schemas/request_response.py
API 요청/응답 스키마 통합
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# 유저 입력
# ============================================================
class UserInputSchema(BaseModel):
    """유저 입력"""
    chat_input: str
    npc_name: Optional[str] = None
    item_name: Optional[str] = None


# ============================================================
# Step (Day) 요청/응답
# ============================================================
class StepRequest(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 요청 바디"""
    user_id: str
    text: str


class StepResponse(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 응답"""
    dialogue: str
    ending: Optional[Dict[str, Any]] = None
    debug: Dict[str, Any] = Field(default_factory=dict)


class TurnResult(BaseModel):
    """낮 파이프라인 실행 결과"""
    narrative: str
    ending_info: Optional[Dict[str, Any]] = None
    state_delta: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Step 요청 (game 라우터용)
# ============================================================
class StepRequestSchema(BaseModel):
    """게임 대화 요청 (game 라우터)"""
    chat_input: str
    npc_name: Optional[str] = None
    item_name: Optional[str] = None

class StepResponseSchema(BaseModel):
    """낮 파이프라인 실행 결과"""
    narrative: str
    ending_info: Optional[Dict[str, Any]] = None
    state_result: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# Night 요청/응답
# ============================================================
class NightRequestBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/night 요청 바디"""
    user_id: str


class NightResponseResult(BaseModel):
    """밤 파이프라인 실행 결과"""
    narrative: str
    ending_info: Optional[Dict[str, Any]] = None
    world_state: Dict[str, Any] = Field(default_factory=dict)
    debug: Dict[str, Any] = Field(default_factory=dict)


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
