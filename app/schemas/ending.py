"""
app/schemas/ending.py
엔딩 체크 관련 스키마
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.game_state import StateDelta


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
    triggered_delta: StateDelta = Field(default_factory=StateDelta)

    def to_ending_info_dict(self) -> Optional[Dict[str, Any]]:
        """파이프라인 응답 스키마(StepResponseSchema, NightResponseResult)의
        ending_info 필드에 바로 넣을 수 있는 dict를 반환합니다.
        엔딩 미도달 시 None을 반환합니다."""
        if not self.reached or self.ending is None:
            return None
        return {
            "ending_id": self.ending.ending_id,
            "name": self.ending.name,
            "epilogue_prompt": self.ending.epilogue_prompt,
        }
