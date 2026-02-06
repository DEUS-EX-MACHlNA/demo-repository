"""
app/agents/memory.py
Memory Stream 관리 — Generative Agents (Park et al. 2023)

각 NPC는 관찰(observation), 성찰(reflection), 계획(plan), 대화(dialogue) 기억을
시간순으로 저장하는 Memory Stream을 갖는다.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Memory Types ─────────────────────────────────────────────
MEMORY_OBSERVATION = "observation"
MEMORY_REFLECTION = "reflection"
MEMORY_PLAN = "plan"
MEMORY_DIALOGUE = "dialogue"


# ── MemoryEntry ──────────────────────────────────────────────
@dataclass
class MemoryEntry:
    """Memory Stream의 단일 항목."""

    memory_id: str
    npc_id: str
    description: str
    creation_turn: int
    last_access_turn: int
    importance_score: float  # 1‑10
    memory_type: str  # observation | reflection | plan | dialogue
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── 직렬화 ───────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # ── 팩토리 ───────────────────────────────────────────────
    @classmethod
    def create(
        cls,
        npc_id: str,
        description: str,
        importance_score: float,
        current_turn: int,
        memory_type: str = MEMORY_OBSERVATION,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
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


# ── Memory Stream helpers ────────────────────────────────────

def get_memory_stream(npc_extras: dict[str, Any]) -> list[MemoryEntry]:
    """NPCState.extras에서 MemoryEntry 리스트를 역직렬화."""
    raw = npc_extras.get("memory_stream", [])
    return [MemoryEntry.from_dict(d) for d in raw]


MAX_MEMORIES_PER_NPC = 100

def set_memory_stream(npc_extras: dict[str, Any], memories: list[MemoryEntry]) -> None:
    """MemoryEntry 리스트를 NPCState.extras에 직렬화. 오래된 항목은 잘라낸다."""
    if len(memories) > MAX_MEMORIES_PER_NPC:
        # 중요도 낮은 오래된 기억부터 제거
        memories.sort(key=lambda m: (m.importance_score, m.creation_turn))
        memories = memories[-MAX_MEMORIES_PER_NPC:]
        memories.sort(key=lambda m: m.creation_turn)
    npc_extras["memory_stream"] = [m.to_dict() for m in memories]


def add_memory(
    npc_extras: dict[str, Any],
    entry: MemoryEntry,
) -> None:
    """단일 기억을 Memory Stream에 추가하고 누적 중요도를 갱신."""
    stream = get_memory_stream(npc_extras)
    stream.append(entry)
    set_memory_stream(npc_extras, stream)

    # 누적 중요도 갱신 (성찰 트리거용)
    acc = npc_extras.get("accumulated_importance", 0.0)
    npc_extras["accumulated_importance"] = acc + entry.importance_score

    logger.debug(
        f"add_memory: npc={entry.npc_id} type={entry.memory_type} "
        f"importance={entry.importance_score:.1f} total_acc={npc_extras['accumulated_importance']:.1f}"
    )
