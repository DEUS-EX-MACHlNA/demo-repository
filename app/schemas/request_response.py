"""
app/schemas/request_response.py
API 요청/응답 스키마
"""
from typing import Any, Dict

from pydantic import BaseModel, Field


class StepRequest(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 요청 바디"""
    user_id: str
    text: str


class StepResponse(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 응답"""
    dialogue: str
    is_observed: bool
    debug: Dict[str, Any] = Field(default_factory=dict)
