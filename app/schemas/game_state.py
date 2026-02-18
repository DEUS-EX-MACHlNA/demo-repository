"""
app/schemas/game_state.py
런타임 게임 상태 스키마

- NPCState: NPC 런타임 상태 (npc_id, stats, memory)
- WorldState: 월드 런타임 전체 상태
- StateDelta: 상태 변경 델타 명세
- merge_deltas: 여러 델타를 하나로 병합
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.status import NPCStatus


class NPCState(BaseModel):
    """NPC 런타임 상태

    NpcSchema(시나리오 정의)와 별개로, 게임 진행 중 변하는 상태만 관리.
    """
    npc_id: str
    status: NPCStatus = NPCStatus.ALIVE
    stats: Dict[str, Any] = Field(default_factory=dict)
    memory: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NPCState:
        """Dict에서 NPCState 생성 (하위 호환성 포함)"""
        npc_id = data.get("npc_id", "unknown")

        stats = data.get("stats", {})
        if not stats:
            stats = {}
            for key in ["trust", "fear", "suspicion", "humanity"]:
                if key in data:
                    stats[key] = data[key]

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

class WorldStatePipeline(BaseModel):
    """월드 런타임 전체 상태"""
    turn: int = 1
    npcs: Dict[str, NPCState] = Field(default_factory=dict)
    flags: Dict[str, Any] = Field(default_factory=dict)
    inventory: List[str] = Field(default_factory=list)
    # item_state_changes

    locks: Dict[str, bool] = Field(default_factory=dict)
    vars: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorldStatePipeline:
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
        )

class WorldState(WorldStatePipeline):
    world_state_pipeline: Dict[str, Any]
    npc_location: Optional[str] = None
    item_state_changes: Optional[str] = None
    npc_disables_states: Optional[str] = None

class StateDelta(BaseModel):
    """상태 변경을 위한 델타 명세

    LLMResponseSchema와 호환:
    - update_vars -> vars
    - update_flags -> flags
    - items_to_add -> inventory_add
    - items_to_remove -> inventory_remove
    """
    npc_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    npc_status_changes: Dict[str, str] = Field(default_factory=dict)
    flags: Dict[str, Any] = Field(default_factory=dict)
    inventory_add: List[str] = Field(default_factory=list)
    inventory_remove: List[str] = Field(default_factory=list)
    locks: Dict[str, bool] = Field(default_factory=dict)
    vars: Dict[str, Any] = Field(default_factory=dict)
    turn_increment: int = 1
    memory_updates: Dict[str, Any] = Field(default_factory=dict)
    next_node: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateDelta:
        return cls(
            npc_stats=data.get("npc_stats", {}),
            npc_status_changes=data.get("npc_status_changes", {}),
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

        merged.npc_status_changes.update(delta.npc_status_changes)
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
