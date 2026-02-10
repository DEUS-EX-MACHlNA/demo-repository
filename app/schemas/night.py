"""
app/schemas/night.py
Night 페이즈 관련 스키마
"""
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel


class NightResult(BaseModel):
    """NightController 실행 결과

    NPC 3명이 함께 나누는 그룹 대화를 담아 반환.
    """
    night_delta: Dict[str, Any]
    night_conversation: List[Dict[str, str]]


class NightExposedLog(BaseModel):
    title: str
    lines: List[str]


class FullLogRef(BaseModel):
    available: bool
    redacted: bool


class PlayerEffect(BaseModel):
    humanityDelta: int
    turnPenaltyNextDay: int
    statusTagsAdded: List[str]


class NpcDelta(BaseModel):
    id: str
    affectionDelta: Optional[int] = 0
    humanityDelta: Optional[int] = 0


class NightEffects(BaseModel):
    player: PlayerEffect
    npcDeltas: List[NpcDelta]


class UiData(BaseModel):
    resultText: str


class NightLogResponse(BaseModel):
    gameId: int
    day: int
    exposedLog: NightExposedLog
    fullLogRef: FullLogRef
    effects: NightEffects
    ui: UiData
    serverTime: datetime
