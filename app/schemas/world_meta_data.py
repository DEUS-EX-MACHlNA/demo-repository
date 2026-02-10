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
    vars: Dict[str, int] = Field(
        default_factory=dict,
        description="현재 변수 값 (예: {'clue_count': 3, 'trust': 10})"
    )
    flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="현재 플래그 상태 (예: {'met_boss': True})"
    )
    active_events: List[str] = Field(
        default_factory=list,
        description="현재 적용 중인 이벤트 ID 목록"
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


class StoryNodeSchema(BaseModel):
    """스토리 노드"""
    node_id: str = Field(..., description="노드 ID")
    summary: str = Field(..., description="씬 요약")
    exit_branches: List[Dict[str, Any]] = Field(default_factory=list, description="분기 정보 리스트")


class StoryGraphSchema(BaseModel):
    """스토리 그래프"""
    nodes: List[StoryNodeSchema]


class EndingSchema(BaseModel):
    """엔딩 정의"""
    ending_id: str
    name: str
    epilogue_prompt: str
    condition: str
    on_enter_events: List[Dict[str, Any]] = Field(default_factory=list)


class ScenarioSchema(BaseModel):
    """시나리오 메타데이터"""
    id: str
    title: str
    genre: str
    tone: str
    pov: str
    turn_limit: int

    global_rules: List[str]
    victory_conditions: List[str]
    failure_conditions: List[str]

    endings: List[EndingSchema]
    state_schema: Dict[str, Any] = Field(..., description="초기 상태 설정 (Vars, Flags, System)")


class WorldDataSchema(BaseModel):
    """월드 데이터 루트 스키마"""
    state: CurrentStateSchema
    scenario: ScenarioSchema
    story_graph: StoryGraphSchema
    locks: LocksSchemaList
    items: ItemsCollectionSchema
