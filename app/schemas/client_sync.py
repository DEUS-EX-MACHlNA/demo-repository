from pydantic import BaseModel, Field
from app.schemas.npc_info import NpcCollectionSchema
from app.schemas.player_info import PlayerSchema
from app.schemas.world_meta_data import WorldDataSchema

class GameClientSyncSchema(BaseModel):
    world: WorldDataSchema = Field(..., description="정적 세계 데이터 및 현재 월드 상태 (시나리오, 맵, 턴 등)")
    player: PlayerSchema = Field(..., description="플레이어의 개인 상태 (인벤토리, 메모, 위치)")
    npcs: NpcCollectionSchema = Field(..., description="모든 NPC의 상태 정보")
