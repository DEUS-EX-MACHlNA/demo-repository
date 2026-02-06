"""
app/schemas/parser.py
파서 관련 스키마
"""
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


class ParsedInput(BaseModel):
    """파서의 출력 결과"""
    intent: str
    target_npc_ids: List[str]
    item_id: str
    content: str
    raw: str
    extraction_method: str = "rule_based"

    @property
    def target_npc_id(self) -> str:
        """하위 호환성: 첫 번째 NPC ID 반환 (없으면 빈 문자열)"""
        return self.target_npc_ids[0] if self.target_npc_ids else ""

    @property
    def target(self) -> Optional[str]:
        """하위 호환성: target_npc_id 또는 item_id 반환"""
        return self.target_npc_id if self.target_npc_id else (self.item_id if self.item_id else None)
