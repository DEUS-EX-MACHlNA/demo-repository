"""
app/schemas/player.py
플레이어 관련 스키마
"""
from typing import List, Dict, Any

from pydantic import BaseModel, Field


class PlayerMemoSchema(BaseModel):
    """플레이어 메모"""
    id: int = Field(..., description="메모 고유 ID")
    text: str = Field(..., description="메모 내용")
    created_at_turn: int = Field(..., description="메모가 작성된 턴")


class PlayerSchema(BaseModel):
    """플레이어 정보"""
    current_node: str = Field(..., description="현재 위치하고 있는 스토리 노드 ID (예: act1_open)")

    # TODO 현재 맵기준과 connected_nodes조건과 비교를 하여 avaliable_nodes를 계산해야함
    # 얜 굳이 있을 필요가 있나..?
    avaliable_nodes: List[str] = Field(default_factory=list, description="현재 접근 가능한 노드 ID 리스트")

    inventory: List[str] = Field(
        default_factory=list,
        description="소지하고 있는 아이템 ID 리스트 (예: ['casefile_brief', ...])"
    )

    memo: List[PlayerMemoSchema] = Field(
        default_factory=list,
        description="플레이어의 수첩(메모) 기록 목록"
    )
    # 여기 안에 humanity를 넣기
    stats: Dict[str, Any] = Field(default_factory=dict, description="플레이어의 현재 상황")

    memory: List[Dict[str, Any]] = Field(default_factory=list, description="LLM용 기억 데이터")
