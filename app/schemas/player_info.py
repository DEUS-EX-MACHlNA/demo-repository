from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# 1. 플레이어 메모 (Memo)
class PlayerMemoSchema(BaseModel):
    id: int = Field(..., description="메모 고유 ID")
    text: str = Field(..., description="메모 내용")
    created_at_turn: int = Field(..., description="메모가 작성된 턴")

# 2. 플레이어 정보 (Player)
class PlayerSchema(BaseModel):
    current_node: str = Field(..., description="현재 위치하고 있는 스토리 노드 ID (예: act1_open)")
    
    inventory: List[str] = Field(
        default_factory=list, 
        description="소지하고 있는 아이템 ID 리스트 (예: ['casefile_brief', ...])"
    )
    
    memo: List[PlayerMemoSchema] = Field(
        default_factory=list, 
        description="플레이어의 수첩(메모) 기록 목록"
    )

    memory: Dict[str, Any] = Field(default_factory=dict, description="LLM용 기억 데이터")
    
    # memory: Optional[dict] = Field(
    #     default_factory=dict,
    #     description="LLM용 기억 데이터"
    # )