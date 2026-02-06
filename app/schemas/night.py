"""
app/schemas/night.py
Night 페이즈 관련 스키마
"""
from typing import Any, Dict, List

from pydantic import BaseModel


class NightResult(BaseModel):
    """NightController 실행 결과

    NPC 3명이 함께 나누는 그룹 대화를 담아 반환.
    """
    night_delta: Dict[str, Any]
    night_conversation: List[Dict[str, str]]
