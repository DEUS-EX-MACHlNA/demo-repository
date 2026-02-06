from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# 이건 그냥 임시임
# 추후 바뀔것임이 틀림없음


class LLMResponseSchema(BaseModel):
    # 1. 텍스트 응답 (NPC 대사, 시스템 나레이션)
    response_text: str 
    
    # 2. 시스템 상태 변경 (변수, 플래그 업데이트)
    update_vars: Dict[str, Any] = {}   # 예: {"trust": 10, "clue_count": 1}
    update_flags: Dict[str, Any] = {}  # 예: {"met_witness": True}
    
    # 3. 인벤토리 변경
    items_to_add: List[str] = []       # 예: ["key_card"]
    items_to_remove: List[str] = []    # 예: ["old_receipt"]
    
    # 4. 메모/기억 업데이트
    new_memo: Optional[str] = None     # 예: "범인은 왼손잡이다."
    update_memory: Dict[str, Any] = {} # LLM 전용 기억 업데이트
    
    # 5. 스토리 이동 (선택)
    next_node: Optional[str] = None    # 예: "act2_scene1" (None이면 현재 위치 유지)