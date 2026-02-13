"""
app/schemas/npc.py
NPC 관련 스키마
"""
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from app.schemas.status import NPCStatus


class NpcSchema(BaseModel):
    """NPC 시나리오 정의 (정적 데이터)"""
    npc_id: str = Field(..., description="NPC 고유 ID (예: family)")
    name: str = Field(..., description="NPC 이름 (예: 피해자 가족)")
    role: str = Field(..., description="NPC 역할 (예: 증언자)")
    user_id: Optional[str] = Field(None, description="연관된 유저 ID")

    stats: Dict[str, int] = Field(..., description="스탯 정보 (Key: 스탯명, Value: 수치)")
    persona: Dict[str, Any] = Field(..., description="성격 및 행동 패턴 (구조 자유)")
    current_node: str = Field(..., description="NPC가 현재 위치하고 있는 스토리 노드 ID")

    # memory: 기억 데이터
    memory: List[Dict[str, Any]] = Field(default_factory=list, description="LLM용 기억 데이터")


class NpcCollectionSchema(BaseModel):
    """NPC 컬렉션"""
    npcs: List[NpcSchema] = Field(..., description="전체 NPC 리스트")
