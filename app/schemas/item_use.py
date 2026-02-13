"""
app/schemas/item_use.py
아이템 사용 관련 스키마

- StatusEffect: 지속시간 기반 상태 효과
- ItemUseResult: 아이템 사용 결과 (룰 엔진 판정 결과)
- AcquisitionResult: 자동 아이템 획득 스캔 결과
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.status import NPCStatus


class StatusEffect(BaseModel):
    """지속시간 기반 NPC status 효과

    set_state 효과에서 duration이 지정된 경우 생성.
    NPC의 status(sleeping, stunned 등)를 변경하고,
    expires_at_turn에 도달하면 original_status로 복구.
    stats(숫자 스탯)는 건드리지 않음.
    """
    effect_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    target_npc_id: str
    applied_status: NPCStatus  # 적용할 상태 (e.g. SLEEPING)
    original_status: NPCStatus = NPCStatus.ALIVE  # 만료 시 복구할 상태
    expires_at_turn: int
    source_item_id: Optional[str] = None
    priority: int = 0


# 아이템 type별 소비 정책
CONSUMABLE_TYPES = frozenset({"consumable", "tool", "gift"})
NON_CONSUMABLE_TYPES = frozenset({
    "key", "lore_clue", "quest_item", "document", "evidence", "permission",
})


class ItemUseResult(BaseModel):
    """아이템 사용 결과 (룰 엔진 판정)"""
    success: bool
    action_id: str = ""
    item_id: str
    failure_reason: Optional[str] = None
    effects_applied: List[Dict[str, Any]] = Field(default_factory=list)
    state_delta: Dict[str, Any] = Field(default_factory=dict)
    status_effects: List[StatusEffect] = Field(default_factory=list)
    item_consumed: bool = False
    notes: str = ""


class AcquisitionResult(BaseModel):
    """자동 아이템 획득 스캔 결과"""
    newly_acquired: List[str] = Field(default_factory=list)
    acquisition_delta: Dict[str, Any] = Field(default_factory=dict)
