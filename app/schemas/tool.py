"""
app/schemas/tool.py
Tool 관련 스키마
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Controller가 결정한 Tool 호출 사양"""
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Tool 실행 결과"""
    state_delta: Dict[str, Any]
    event_description: List[str]
    intent: str = "neutral"
    npc_response: Optional[str] = None # interact()만 존재
    npc_id: Optional[str]  = None      # interact()만 존재
    item_id: Optional[str] = None      # use()만 존재
    ending_info: Optional[Dict[str, Any]] = None  # use()에서 엔딩 트리거 시 존재