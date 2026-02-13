"""
app/schemas/night_response.py
밤 페이즈 응답 스키마
"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class NightDialogue(BaseModel):
    speaker_name: str = Field(..., description="화자 이름 (예: 엘리노어 (새엄마))")
    dialogue: str = Field(..., description="대사 내용")

class NightResponse(BaseModel):
    narrative: str = Field(..., description="별도의 요청 없이 표시될 밤 이야기 개요")
    dialogues: List[NightDialogue] = Field(..., description="밤 대화 리스트")
    npc_state_results: Dict[str, Dict[str, int]] = Field(..., description="NPC 상태 결과 (Key: NPC ID, Value: {stat_name: value})")
    ending_info: Optional[Dict[str, Any]] = None
    vars: Optional[Dict[str, Any]]
