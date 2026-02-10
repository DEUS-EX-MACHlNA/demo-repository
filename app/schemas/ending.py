"""
app/schemas/ending.py
엔딩 체크 관련 스키마
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EndingInfo(BaseModel):
    """도달한 엔딩 정보"""
    ending_id: str
    name: str
    epilogue_prompt: str
    on_enter_events: List[Dict[str, Any]] = Field(default_factory=list)


class EndingCheckResult(BaseModel):
    """엔딩 체크 결과"""
    reached: bool
    ending: Optional[EndingInfo] = None
    triggered_delta: Dict[str, Any] = Field(default_factory=dict)
