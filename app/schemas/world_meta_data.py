"""
app/schemas/world_data.py
시나리오 월드 구조 스키마 (정적 데이터)
"""
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from app.schemas.item_info import ItemsCollectionSchema


class CurrentStateSchema(BaseModel):
    """현재 게임의 동적 상태 (시나리오 초기값 정의)"""
    turn: int = Field(..., description="현재 턴")
    date: int = Field(..., description="현재 날짜")

    # 2. 변수와 플래그 (가장 중요!)
    # 여기는 값이 계속 변하므로 Dict[str, Any]로 유연하게 받습니다.

    vars: Dict[str, int] = Field(
        default_factory=dict,
        description="현재 변수 값 (예: {'clue_count': 3, 'trust': 10})"
    )
    flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="현재 플래그 상태 (예: {'met_boss': True})"
    )

class LockSchema(BaseModel):
    """잠금 정보"""
    info_id: str = Field(..., description="정보 ID")
    info_title: str = Field(..., description="제목")
    description: str = Field(..., description="내용")
    is_unlocked: bool = Field(default=False, description="해금 여부")

    linked_info_id: Optional[str] = Field(None, description="연결된 정보 ID")
    unlock_condition: Optional[str] = Field(None, description="해금 조건식")
    reveal_trigger: Optional[str] = Field(None, description="해금 트리거")

    access: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="접근 권한 설정 (예: {'allowed_npcs': ['partner']})"
    )

    class Config:
        extra = "allow"


class LocksSchemaList(BaseModel):
    """잠금 정보 리스트"""
    locks: List[LockSchema]

# =========================================================
# 3. [Scenario] 시나리오 메타 & 룰
#    - 제목, 장르 등 메타데이터는 엄격하게
#    - 엔딩 조건이나 초기 상태값(State Schema)은 유연하게
# =========================================================
class EndingSchema(BaseModel):
    """엔딩 정의"""
    ending_id: str
    name: str
    epilogue_prompt: str


class ScenarioSchema(BaseModel):
    # [Strict] 규칙 (텍스트 리스트라 구조가 단순함)
    global_rules: List[str]
    victory_conditions: List[str]
    failure_conditions: List[str]

    endings: List[EndingSchema]


class WorldDataSchema(BaseModel):
    """월드 데이터 루트 스키마"""
    state: CurrentStateSchema
    scenario: ScenarioSchema
    locks: LocksSchemaList
    items: ItemsCollectionSchema
