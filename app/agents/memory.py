"""
app/agents/memory.py
Memory Stream 관리 — Generative Agents (Park et al. 2023)

각 NPC는 관찰(observation), 성찰(reflection), 계획(plan), 대화(dialogue) 기억을
시간순으로 저장하는 Memory Stream을 갖는다.

schemas/memory.py의 MemoryEntrySchema를 사용하여 Pydantic 기반으로 통합됨.
NPCState.memory (이전의 NPCState.extras)에 저장.
"""
from __future__ import annotations

import logging
from typing import Any, List, Union

# schemas에서 Memory 관련 스키마 import
from app.schemas import (
    MemoryEntrySchema,
    MemoryStreamSchema,
    MEMORY_OBSERVATION,
    MEMORY_REFLECTION,
    MEMORY_PLAN,
    MEMORY_DIALOGUE,
    MAX_MEMORIES_PER_NPC,
)

logger = logging.getLogger(__name__)

# 하위 호환성을 위한 re-export
MemoryEntry = MemoryEntrySchema


# ── Memory Stream helpers ────────────────────────────────────
def get_memory_stream(npc_memory: dict[str, Any]) -> list[MemoryEntrySchema]:
    """NPCState.memory에서 MemoryEntrySchema 리스트를 역직렬화.

    Args:
        npc_memory: NPCState.memory dict (이전의 npc_extras)

    Returns:
        MemoryEntrySchema 리스트
    """
    raw = npc_memory.get("memory_stream", [])
    result = []
    for d in raw:
        try:
            if isinstance(d, dict):
                result.append(MemoryEntrySchema(**d))
            elif isinstance(d, MemoryEntrySchema):
                result.append(d)
        except Exception as e:
            logger.warning(f"Failed to parse memory entry: {e}")
            continue
    return result


def set_memory_stream(npc_memory: dict[str, Any], memories: list[MemoryEntrySchema]) -> None:
    """MemoryEntrySchema 리스트를 NPCState.memory에 직렬화. 오래된 항목은 잘라낸다.

    Args:
        npc_memory: NPCState.memory dict
        memories: 저장할 메모리 리스트
    """
    if len(memories) > MAX_MEMORIES_PER_NPC:
        # 중요도 낮은 오래된 기억부터 제거
        memories.sort(key=lambda m: (m.importance_score, m.creation_turn))
        memories = memories[-MAX_MEMORIES_PER_NPC:]
        memories.sort(key=lambda m: m.creation_turn)

    # Pydantic 모델을 dict로 변환하여 저장
    serialized = []
    for m in memories:
        if hasattr(m, 'model_dump'):
            serialized.append(m.model_dump())
        elif hasattr(m, 'dict'):
            serialized.append(m.dict())
        else:
            serialized.append(m)
    npc_memory["memory_stream"] = serialized


def add_memory(
    npc_memory: dict[str, Any],
    entry: MemoryEntrySchema,
) -> None:
    """단일 기억을 Memory Stream에 추가.

    Args:
        npc_memory: NPCState.memory dict
        entry: 추가할 메모리 엔트리
    """
    stream = get_memory_stream(npc_memory)
    stream.append(entry)
    set_memory_stream(npc_memory, stream)

    logger.debug(
        f"add_memory: npc={entry.npc_id} type={entry.memory_type} "
        f"importance={entry.importance_score:.1f}"
    )


def create_memory(
    npc_id: str,
    description: str,
    importance_score: float,
    current_turn: int,
    memory_type: str = MEMORY_OBSERVATION,
    metadata: dict[str, Any] | None = None,
) -> MemoryEntrySchema:
    """새 메모리 엔트리 생성 (팩토리 함수).

    Args:
        npc_id: NPC ID
        description: 메모리 내용
        importance_score: 중요도 (1-10)
        current_turn: 현재 턴
        memory_type: 메모리 타입
        metadata: 추가 메타데이터

    Returns:
        MemoryEntrySchema 인스턴스
    """
    return MemoryEntrySchema.create(
        npc_id=npc_id,
        description=description,
        importance_score=importance_score,
        current_turn=current_turn,
        memory_type=memory_type,
        metadata=metadata,
    )


