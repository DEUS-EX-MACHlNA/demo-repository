from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

# =========================================================
# 1. [Arg 1] 유저 입력 (User Input)
# =========================================================
class UserInputSchema(BaseModel):
    chat_input: str
    npc_name: Optional[str] = None
    item_name: Optional[str] = None


# =========================================================
# 2. [Arg 2] 월드 정보 (World Info) - 뼈대만 검증
# =========================================================

from app.schemas.npc_info import NpcCollectionSchema
from app.schemas.player_info import PlayerSchema

# --- Items ---
class ItemSchema(BaseModel):
    item_id: str
    name: str
    type: str
    description: str
    # acquire, use 안에 actions, effects 등 복잡한 건 그냥 dict로 받음
    # 이렇게 하면 내부 구조가 조금 바뀌어도 에러가 안 남!
    acquire: Dict[str, Any] 
    use: Dict[str, Any]

class ItemCollectionSchema(BaseModel):
    items: List[ItemSchema]

# --- Arg 2 Wrapper ---
class WorldInfoSchema(BaseModel):
    player: PlayerSchema
    npcs: NpcCollectionSchema    # {"npcs": [...]} 구조 대응
    items: ItemCollectionSchema  # {"items": [...]} 구조 대응


# =========================================================
# 3. [Arg 3] 로직 컨텍스트 (Logic Context) - 대부분 유연하게
# =========================================================
class LogicContextSchema(BaseModel):
    # 메타 정보는 구조가 단순하니 정의해도 좋음
    meta: Dict[str, Any] 
    
    # State는 중요 변수들이라 최소한의 타입 체크
    state: Dict[str, Any] # {"vars": {...}, "system": {...}}
    
    # Rules(엔딩, 승리조건)는 너무 복잡하므로 통으로 dict 처리
    rules: Dict[str, Any]


# =========================================================
# 4. [Arg 4] 모델 설정 (Model Config)
# =========================================================
class ModelConfigSchema(BaseModel):
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    extra_settings: Dict[str, Any] = Field(default_factory=dict)


# =========================================================
# 👑 [ROOT] 최종 페이로드 (Final Payload)
# =========================================================
class LLMInputPayload(BaseModel):
    arg1_user_input: UserInputSchema
    arg2_world_info: WorldInfoSchema
    arg3_logic_context: LogicContextSchema
    arg4_model_config: ModelConfigSchema