from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.schemas.status import NPCStatus

class NpcSchema(BaseModel):
    # 1. [Strict] 프론트엔드에서 UI를 그릴 때 꼭 필요한 정보
    npc_id: str = Field(..., description="NPC 고유 ID (예: family)")
    name: str = Field(..., description="NPC 이름 (예: 피해자 가족)")
    role: str = Field(..., description="NPC 역할 (예: 증언자)")
    user_id: Optional[str] = Field(None, description="연관된 유저 ID")
    status: NPCStatus = Field(
        default=NPCStatus.ALIVE, 
        description="NPC 상태 (예: alive, deceased 등)")

    # 2. [Flexible] 게임 밸런싱/기획 변경이 잦은 데이터는 Dict로 유연하게 처리
    
    # stats: "trust", "fear" 등을 일일이 정의하지 않고 {문자열: 숫자} 맵으로 받음
    stats: Dict[str, int] = Field(..., description="스탯 정보 (Key: 스탯명, Value: 수치)")
    
    # persona: values, taboos, triggers 등 복잡한 중첩 구조를 통으로 받음
    persona: Dict[str, Any] = Field(..., description="성격 및 행동 패턴 (구조 자유)")
    
    # current_code = npc의 현재 위치
    current_node: str = Field(..., description="NPC가 현재 위치하고 있는 스토리 노드 ID")

    # memory: 기억 데이터
    memory: Dict[str, Any] = Field(default_factory=dict, description="LLM용 기억 데이터")

class NpcCollectionSchema(BaseModel):
    # 최상위 리스트 구조는 유지
    npcs: List[NpcSchema] = Field(..., description="전체 NPC 리스트")