"""
app/schemas/client_sync.py
클라이언트 동기화 스키마
"""

from pydantic import BaseModel, Field

class GameClientSyncSchema(BaseModel):
    game_id: int = Field(..., description="게임 ID")
    user_id: int = Field(..., description="유저 ID")
