"""
app/schemas/core.py
핵심 엔티티 스키마 (Enums, NPC, Player, Item)
"""
from enum import Enum
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================
class NPCStatus(str, Enum):
    """NPC 상태"""
    ALIVE = "alive"
    DECEASED = "deceased"
    MISSING = "missing"
    UNKNOWN = "unknown"


class Intent(str, Enum):
    """파싱된 의도 타입"""
    LEADING = "leading"
    NEUTRAL = "neutral"
    EMPATHIC = "empathic"
    SUMMARIZE = "summarize"
    UNKNOWN = "unknown"


class ToolName(str, Enum):
    """사용 가능한 Tool 이름"""
    NPC_TALK = "npc_talk"
    ACTION = "action"
    ITEM_USAGE = "item_usage"


# ============================================================
# NPC
# ============================================================
class NpcSchema(BaseModel):
    """NPC 시나리오 정의 (정적 데이터)"""
    npc_id: str = Field(..., description="NPC 고유 ID (예: family)")
    name: str = Field(..., description="NPC 이름 (예: 피해자 가족)")
    role: str = Field(..., description="NPC 역할 (예: 증언자)")
    user_id: Optional[str] = Field(None, description="연관된 유저 ID")
    status: NPCStatus = Field(
        default=NPCStatus.ALIVE,
        description="NPC 상태 (예: alive, deceased 등)")

    stats: Dict[str, int] = Field(..., description="스탯 정보 (Key: 스탯명, Value: 수치)")
    persona: Dict[str, Any] = Field(..., description="성격 및 행동 패턴 (구조 자유)")
    current_node: str = Field(..., description="NPC가 현재 위치하고 있는 스토리 노드 ID")
    memory: Dict[str, Any] = Field(default_factory=dict, description="LLM용 기억 데이터")


class NpcCollectionSchema(BaseModel):
    """NPC 컬렉션"""
    npcs: List[NpcSchema] = Field(..., description="전체 NPC 리스트")


# ============================================================
# Player
# ============================================================
class PlayerMemoSchema(BaseModel):
    """플레이어 메모"""
    id: int = Field(..., description="메모 고유 ID")
    text: str = Field(..., description="메모 내용")
    created_at_turn: int = Field(..., description="메모가 작성된 턴")


class PlayerSchema(BaseModel):
    """플레이어 정보"""
    current_node: str = Field(..., description="현재 위치하고 있는 스토리 노드 ID (예: act1_open)")

    inventory: List[str] = Field(
        default_factory=list,
        description="소지하고 있는 아이템 ID 리스트 (예: ['casefile_brief', ...])"
    )

    memo: List[PlayerMemoSchema] = Field(
        default_factory=list,
        description="플레이어의 수첩(메모) 기록 목록"
    )

    memory: Dict[str, Any] = Field(default_factory=dict, description="LLM용 기억 데이터")


# ============================================================
# Item
# ============================================================
class ItemSchema(BaseModel):
    """아이템 정의"""
    item_id: str = Field(..., description="아이템 고유 ID")
    name: str = Field(..., description="아이템 이름")
    type: str = Field(..., description="아이템 타입")
    description: str = Field(..., description="아이템 설명")

    acquire: Dict[str, Any] = Field(..., description="획득 조건 로직 (구조 자유)")
    use: Dict[str, Any] = Field(..., description="사용 효과 및 행동 로직 (구조 자유)")


class ItemsCollectionSchema(BaseModel):
    """아이템 컬렉션"""
    items: List[ItemSchema] = Field(..., description="전체 아이템 리스트")
