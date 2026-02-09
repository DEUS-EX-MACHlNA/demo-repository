"""
app/schemas/state.py
상태 관련 스키마 (GameState, Memory, WorldData)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid

from app.schemas.core import ItemsCollectionSchema


# ============================================================
# Memory
# ============================================================
MEMORY_OBSERVATION = "observation"
MEMORY_REFLECTION = "reflection"
MEMORY_PLAN = "plan"
MEMORY_DIALOGUE = "dialogue"
MAX_MEMORIES_PER_NPC = 100


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
        extra = "allow"

    @classmethod
    def create(
        cls,
        npc_id: str,
        description: str,
        importance_score: float,
        current_turn: int,
        memory_type: str = MEMORY_OBSERVATION,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntrySchema:
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


# ============================================================
# Game State (Runtime)
# ============================================================
class NPCState(BaseModel):
    """NPC 런타임 상태

    NpcSchema(시나리오 정의)와 별개로, 게임 진행 중 변하는 상태만 관리.
    """
    npc_id: str
    stats: Dict[str, int] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NPCState:
        """Dict에서 NPCState 생성 (하위 호환성 포함)"""
        npc_id = data.get("npc_id", "unknown")

        stats = data.get("stats", {})
        if not stats:
            # 하위 호환: stats Dict가 없으면 최상위 int 값을 stats로 마이그레이션
            reserved_keys = {"npc_id", "memory", "extras", "stats"}
            stats = {
                k: v for k, v in data.items()
                if k not in reserved_keys and isinstance(v, (int, float))
            }

        memory = data.get("memory", {})
        if not memory:
            extras = data.get("extras", {})
            if extras:
                memory = extras.copy()

        return cls(npc_id=npc_id, stats=stats, memory=memory)

    def get_stat(self, key: str, default: int = 0) -> int:
        return self.stats.get(key, default)

    def set_stat(self, key: str, value: int) -> None:
        self.stats[key] = value

    def add_stat(self, key: str, delta: int, min_val: int = 0, max_val: int = 100) -> int:
        current = self.stats.get(key, 0)
        new_value = max(min_val, min(max_val, current + delta))
        self.stats[key] = new_value
        return new_value


class WorldState(BaseModel):
    """월드 런타임 전체 상태"""
    turn: int = 1
    npcs: Dict[str, NPCState] = Field(default_factory=dict)
    flags: Dict[str, Any] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    locks: Dict[str, bool] = Field(default_factory=dict)
    vars: Dict[str, Any] = Field(default_factory=dict)
    active_events: List[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldState:
        npcs = {}
        for npc_id, npc_data in data.get("npcs", {}).items():
            if isinstance(npc_data, dict):
                npc_data["npc_id"] = npc_id
                npcs[npc_id] = NPCState.from_dict(npc_data)

        return cls(
            turn=data.get("turn", 1),
            npcs=npcs,
            flags=data.get("flags", {}),
            inventory=data.get("inventory", []),
            locks=data.get("locks", {}),
            vars=data.get("vars", {}),
            active_events=data.get("active_events", []),
        )


class StateDelta(BaseModel):
    """상태 변경을 위한 델타 명세

    LLMResponseSchema와 호환:
    - update_vars -> vars
    - update_flags -> flags
    - items_to_add -> inventory_add
    - items_to_remove -> inventory_remove
    """
    npc_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    flags: Dict[str, Any] = Field(default_factory=dict)
    inventory_add: List[str] = Field(default_factory=list)
    inventory_remove: List[str] = Field(default_factory=list)
    locks: Dict[str, bool] = Field(default_factory=dict)
    vars: Dict[str, Any] = Field(default_factory=dict)
    turn_increment: int = 0
    memory_updates: Dict[str, Any] = Field(default_factory=dict)
    next_node: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateDelta:
        return cls(
            npc_stats=data.get("npc_stats", {}),
            flags=data.get("flags", data.get("update_flags", {})),
            inventory_add=data.get("inventory_add", data.get("items_to_add", [])),
            inventory_remove=data.get("inventory_remove", data.get("items_to_remove", [])),
            locks=data.get("locks", {}),
            vars=data.get("vars", data.get("update_vars", {})),
            turn_increment=data.get("turn_increment", 0),
            memory_updates=data.get("memory_updates", data.get("update_memory", {})),
            next_node=data.get("next_node"),
        )

    @classmethod
    def from_llm_response(cls, llm_response: dict[str, Any]) -> StateDelta:
        """LLMResponseSchema dict에서 StateDelta 생성"""
        return cls(
            flags=llm_response.get("update_flags", {}),
            inventory_add=llm_response.get("items_to_add", []),
            inventory_remove=llm_response.get("items_to_remove", []),
            vars=llm_response.get("update_vars", {}),
            memory_updates=llm_response.get("update_memory", {}),
            next_node=llm_response.get("next_node"),
        )


def merge_deltas(*deltas: dict[str, Any]) -> dict[str, Any]:
    """여러 델타를 하나로 병합"""
    merged = StateDelta()

    for delta_dict in deltas:
        delta = StateDelta.from_dict(delta_dict) if isinstance(delta_dict, dict) else delta_dict

        for npc_id, stats in delta.npc_stats.items():
            if npc_id not in merged.npc_stats:
                merged.npc_stats[npc_id] = {}
            for stat, value in stats.items():
                merged.npc_stats[npc_id][stat] = merged.npc_stats[npc_id].get(stat, 0) + value

        merged.flags.update(delta.flags)
        merged.inventory_add.extend(delta.inventory_add)
        merged.inventory_remove.extend(delta.inventory_remove)
        merged.locks.update(delta.locks)

        for key, value in delta.vars.items():
            if key in merged.vars and isinstance(merged.vars[key], (int, float)) and isinstance(value, (int, float)):
                merged.vars[key] += value
            else:
                merged.vars[key] = value

        merged.memory_updates.update(delta.memory_updates)
        merged.turn_increment += delta.turn_increment

        if delta.next_node:
            merged.next_node = delta.next_node

    return merged.to_dict()


# ============================================================
# World Data (Static Scenario Structure)
# ============================================================
class CurrentStateSchema(BaseModel):
    """현재 게임의 동적 상태 (시나리오 초기값 정의)"""
    turn: int = Field(..., description="현재 턴")
    vars: Dict[str, int] = Field(
        default_factory=dict,
        description="현재 변수 값 (예: {'clue_count': 3, 'trust': 10})"
    )
    flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="현재 플래그 상태 (예: {'met_boss': True})"
    )
    active_events: List[str] = Field(
        default_factory=list,
        description="현재 적용 중인 이벤트 ID 목록"
    )


class LockSchema(BaseModel):
    """잠금 정보"""
    info_id: str = Field(..., description="정보 ID")
    info_title: str = Field(..., description="제목")
    description: str = Field(..., description="내용")
    is_unlocked: bool = Field(default=False, description="해금 여부")

    linked_info_id: Optional[str] = Field(None, description="연결된 정보 ID")
    unlock_condition: Optional[str] = Field(None, description="해금 조건식")
    reveal_trigger: Optional[str] = Field(None, description="해금 트리거")

    access: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="접근 권한 설정 (예: {'allowed_npcs': ['partner']})"
    )

    class Config:
        extra = "allow"


class LocksSchemaList(BaseModel):
    """잠금 정보 리스트"""
    locks: List[LockSchema]


class StoryNodeSchema(BaseModel):
    """스토리 노드"""
    node_id: str = Field(..., description="노드 ID")
    summary: str = Field(..., description="씬 요약")
    exit_branches: List[Dict[str, Any]] = Field(default_factory=list, description="분기 정보 리스트")


class StoryGraphSchema(BaseModel):
    """스토리 그래프"""
    nodes: List[StoryNodeSchema]


class EndingSchema(BaseModel):
    """엔딩 정의"""
    ending_id: str
    name: str
    epilogue_prompt: str
    condition: str
    on_enter_events: List[Dict[str, Any]] = Field(default_factory=list)


class ScenarioSchema(BaseModel):
    """시나리오 메타데이터"""
    id: str
    title: str
    genre: str
    tone: str
    pov: str
    turn_limit: int

    global_rules: List[str]
    victory_conditions: List[str]
    failure_conditions: List[str]

    endings: List[EndingSchema]
    state_schema: Dict[str, Any] = Field(..., description="초기 상태 설정 (Vars, Flags, System)")


class WorldDataSchema(BaseModel):
    """월드 데이터 루트 스키마"""
    state: CurrentStateSchema
    scenario: ScenarioSchema
    story_graph: StoryGraphSchema
    locks: LocksSchemaList
    items: ItemsCollectionSchema
