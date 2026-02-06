"""
app/schemas/llm_response.py
LLM 응답 스키마
"""
from typing import List, Dict, Any, Optional

from pydantic import BaseModel


class LLMResponseSchema(BaseModel):
    """LLM 응답"""
    response_text: str

    update_vars: Dict[str, Any] = {}
    update_flags: Dict[str, Any] = {}

    items_to_add: List[str] = []
    items_to_remove: List[str] = []

    new_memo: Optional[str] = None
    update_memory: Dict[str, Any] = {}

    next_node: Optional[str] = None
