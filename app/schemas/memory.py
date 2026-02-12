"""
app/schemas/memory.py
Memory Entry Schema - Generative Agents (Park et al. 2023) 기반

Pydantic BaseModel로 정의하여 기존 MemoryEntry 기능을 유지하면서
schemas 체계와 통합합니다.
"""
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
import uuid


# ── Memory Types ─────────────────────────────────────────────
MEMORY_OBSERVATION = "observation"
MEMORY_REFLECTION = "reflection"
MEMORY_PLAN = "plan"
MEMORY_DIALOGUE = "dialogue"


class MemoryEntrySchema(BaseModel):
    """Memory Stream의 단일 항목 (Pydantic 기반)"""

    memory_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="메모리 고유 ID")
    npc_id: str = Field(..., description="NPC ID")
    description: str = Field(..., description="메모리 내용")
    creation_turn: int = Field(..., description="생성된 턴")
    last_access_turn: int = Field(..., description="마지막 접근 턴")
    importance_score: float = Field(..., ge=1, le=10, description="중요도 (1-10)")
    memory_type: str = Field(
        default=MEMORY_OBSERVATION,
        description="메모리 타입 (observation | reflection | plan | dialogue)"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")

    class Config:
        extra = "allow"  # 추가 필드 허용

    @classmethod
    def create(
        cls,
        npc_id: str,
        description: str,
        importance_score: float,
        current_turn: int,
        memory_type: str = MEMORY_OBSERVATION,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "MemoryEntrySchema":
        """팩토리 메서드: 새 메모리 엔트리 생성"""
        return cls(
            memory_id=str(uuid.uuid4()),
            npc_id=npc_id,
            description=description,
            creation_turn=current_turn,
            last_access_turn=current_turn,
            importance_score=importance_score,
            memory_type=memory_type,
            metadata=metadata or {},
        )


class MemoryStreamSchema(BaseModel):
    """NPC의 전체 Memory Stream"""

    memories: List[MemoryEntrySchema] = Field(default_factory=list, description="메모리 엔트리 리스트")
    accumulated_importance: float = Field(default=0.0, description="누적 중요도 (성찰 트리거용)")

    class Config:
        extra = "allow"


# ── Memory Stream 상수 ────────────────────────────────────────
MAX_MEMORIES_PER_NPC = 100
