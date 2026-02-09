from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime

class NpcId(str, Enum):
    STEPMOTHER = "stepmother"
    STEPFATHER = "stepfather"
    BROTHER = "brother"
    DOG = "dog"
    GRANDMOTHER = "grandmother"

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
    id: str # Using str to be flexible, or NpcId
    affectionDelta: Optional[int] = 0
    humanityDelta: Optional[int] = 0

class NightEffects(BaseModel):
    player: PlayerEffect
    npcDeltas: List[NpcDelta]

class UiData(BaseModel):
    resultText: str

class NightLogResponse(BaseModel):
    nightId: str
    gameId: int
    day: int
    exposedLog: NightExposedLog
    fullLogRef: FullLogRef
    effects: NightEffects
    ui: UiData
    serverTime: datetime
