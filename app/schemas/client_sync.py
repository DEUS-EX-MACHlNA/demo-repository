"""
app/schemas/client_sync.py
클라이언트 동기화 스키마
"""
from pydantic import BaseModel, Field

from app.schemas.npc import NpcCollectionSchema
from app.schemas.player import PlayerSchema
from app.schemas.world_data import WorldDataSchema


class GameClientSyncSchema(BaseModel):
    world: WorldDataSchema = Field(..., description="정적 세계 데이터 및 현재 월드 상태 (시나리오, 맵, 턴 등)")
    player: PlayerSchema = Field(..., description="플레이어의 개인 상태 (인벤토리, 메모, 위치)")
    npcs: NpcCollectionSchema = Field(..., description="모든 NPC의 상태 정보")
