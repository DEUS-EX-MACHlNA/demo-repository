"""
app/schemas/condition.py
조건 평가 관련 스키마
"""
from typing import Any, Dict

from pydantic import BaseModel, Field

from app.schemas.game_state import WorldState


class EvalContext(BaseModel):
    """조건 평가에 필요한 컨텍스트"""
    world_state: WorldState
    turn_limit: int = 50
    extra_vars: Dict[str, Any] = Field(default_factory=dict)
