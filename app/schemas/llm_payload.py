"""
app/schemas/llm_payload.py
LLM 입력 페이로드 스키마

메인 스키마(npc.py, player.py, item.py)를 재사용하여 중복 제거.
"""
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field

from app.schemas.npc import NpcCollectionSchema
from app.schemas.player import PlayerSchema
from app.schemas.item import ItemsCollectionSchema


class UserInputSchema(BaseModel):
    """유저 입력"""
    chat_input: str
    npc_name: Optional[str] = None
    item_name: Optional[str] = None

    def to_combined_string(self) -> str:
        """
        UserInputSchema를 단일 문자열로 변환합니다.

        chat_input에 npc_name, item_name 정보를 자연스럽게 결합합니다.

        Returns:
            결합된 문자열
        """
        parts = [self.chat_input]

        if self.npc_name:
            parts.append(f"(대상 NPC: {self.npc_name})")

        if self.item_name:
            parts.append(f"(대상 아이템: {self.item_name})")

        return " ".join(parts)


class WorldInfoSchema(BaseModel):
    """월드 정보 (LLM에 전달)"""
    player: PlayerSchema
    npcs: NpcCollectionSchema
    items: ItemsCollectionSchema


class LogicContextSchema(BaseModel):
    """로직 컨텍스트"""
    meta: Dict[str, Any]
    state: Dict[str, Any]
    rules: Dict[str, Any]


class ModelConfigSchema(BaseModel):
    """모델 설정"""
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    extra_settings: Dict[str, Any] = Field(default_factory=dict)


class LLMInputPayload(BaseModel):
    """최종 LLM 페이로드"""
    arg1_user_input: UserInputSchema
    arg2_world_info: WorldInfoSchema
    arg3_logic_context: LogicContextSchema
    arg4_model_config: ModelConfigSchema
