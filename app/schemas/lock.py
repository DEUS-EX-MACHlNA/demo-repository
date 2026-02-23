"""
app/schemas/lock.py
Lock 체크 관련 스키마
"""
from typing import List, Optional, Set

from pydantic import BaseModel, Field


class UnlockedInfo(BaseModel):
    """해금된 정보"""
    info_id: str
    type: str
    info_title: str
    description: str
    allowed_npcs: List[str] = Field(default_factory=list)


class LockCheckResult(BaseModel):
    """Lock 체크 결과"""
    newly_unlocked: List[UnlockedInfo]
    all_unlocked_ids: Set[str]
