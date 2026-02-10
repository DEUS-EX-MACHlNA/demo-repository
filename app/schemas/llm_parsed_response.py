"""
app/schemas/llm_parsed_response.py
LLM 응답 파싱 결과 스키마
"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class LLMParsedResponse(BaseModel):
    """LLM 응답 파싱 결과"""
    raw_text: str
    cleaned_text: str
    state_delta: dict[str, Any] = Field(default_factory=dict)
    event_description: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
