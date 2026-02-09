from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any

class NightChatResponse(BaseModel):
    gameId: int
    day: int
    exposedLog: Dict[str, Any]
    fullLogRef: Dict[str, Any]
    effects: Dict[str, Any]
    ui: Dict[str, Any]
    serverTime: datetime