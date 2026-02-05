"""
app/models.py
공통 데이터 모델 정의
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


# ============================================================
# Request/Response Models
# ============================================================
@dataclass
class StepRequest:
    """POST /v1/scenario/{scenario_id}/step 요청 바디"""
    user_id: str
    text: str


@dataclass
class StepResponse:
    """POST /v1/scenario/{scenario_id}/step 응답"""
    dialogue: str
    is_observed: bool
    debug: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Parser Models
# ============================================================
class Intent(str, Enum):
    """파싱된 의도 타입"""
    LEADING = "leading"
    NEUTRAL = "neutral"
    EMPATHIC = "empathic"
    SUMMARIZE = "summarize"
    UNKNOWN = "unknown"


@dataclass
class ParsedInput:
    """파서의 출력 결과"""
    intent: str  # Intent enum value
    target_npc_ids: list[str]  # NPC ID 리스트 (빈 리스트면 NPC 대상 아님)
    item_id: str  # item ID (빈 문자열이면 아이템 사용 아님)
    content: str  # 정제된 내용
    raw: str  # 원본 텍스트
    extraction_method: str = "rule_based"  # rule_based | lm_based | prespecified

    # 하위 호환성을 위한 프로퍼티들
    @property
    def target_npc_id(self) -> str:
        """하위 호환성: 첫 번째 NPC ID 반환 (없으면 빈 문자열)"""
        return self.target_npc_ids[0] if self.target_npc_ids else ""

    @property
    def target(self) -> Optional[str]:
        """하위 호환성: target_npc_id 또는 item_id 반환"""
        return self.target_npc_id if self.target_npc_id else (self.item_id if self.item_id else None)


# ============================================================
# World State Models
# ============================================================
@dataclass
class NPCState:
    """NPC 상태"""
    npc_id: str
    trust: int = 0
    fear: int = 0
    suspicion: int = 0
    humanity: int = 10  # 인간성 (0이면 인형화)
    # 추가 커스텀 필드를 위한 extras
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "npc_id": self.npc_id,
            "trust": self.trust,
            "fear": self.fear,
            "suspicion": self.suspicion,
            "humanity": self.humanity,
            **self.extras
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NPCState:
        known_keys = {"npc_id", "trust", "fear", "suspicion", "humanity"}
        extras = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            npc_id=data.get("npc_id", "unknown"),
            trust=data.get("trust", 0),
            fear=data.get("fear", 0),
            suspicion=data.get("suspicion", 0),
            humanity=data.get("humanity", 10),
            extras=extras
        )


@dataclass
class WorldState:
    """월드 상태 전체"""
    turn: int = 1
    npcs: dict[str, NPCState] = field(default_factory=dict)  # npc_id -> NPCState
    flags: dict[str, Any] = field(default_factory=dict)
    inventory: list[str] = field(default_factory=list)  # item_id 리스트
    locks: dict[str, bool] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)  # scenario-specific variables

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "npcs": {npc_id: npc.to_dict() for npc_id, npc in self.npcs.items()},
            "flags": self.flags.copy(),
            "inventory": self.inventory.copy(),
            "locks": self.locks.copy(),
            "vars": self.vars.copy()
        }

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
            vars=data.get("vars", {})
        )


# ============================================================
# Tool Models
# ============================================================
class ToolName(str, Enum):
    """사용 가능한 Tool 이름"""
    NPC_TALK = "npc_talk"
    ACTION = "action"
    ITEM_USAGE = "item_usage"


@dataclass
class ToolCall:
    """Controller가 결정한 Tool 호출 사양"""
    tool_name: str  # ToolName value
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Tool 실행 결과"""
    state_delta: dict[str, Any]  # WorldState에 적용할 델타
    event_description: list[str]  # 발생 사건들의 묘사 리스트


@dataclass
class NightResult:
    """NightController 실행 결과

    NPC 3명이 함께 나누는 그룹 대화를 담아 반환.
    """
    night_delta: dict[str, Any]
    night_conversation: list[dict[str, str]]  # [{speaker, text}, ...] 그룹 대화


# ============================================================
# State Delta Models
# ============================================================
@dataclass
class StateDelta:
    """상태 변경을 위한 델타 명세"""
    # NPC 스탯 변경: {npc_id: {stat_name: delta_value}}
    npc_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    # 플래그 설정: {key: value}
    flags: dict[str, Any] = field(default_factory=dict)
    # 인벤토리 추가
    inventory_add: list[str] = field(default_factory=list)
    # 인벤토리 제거
    inventory_remove: list[str] = field(default_factory=list)
    # 잠금 상태 변경
    locks: dict[str, bool] = field(default_factory=dict)
    # 시나리오 변수 변경: {var_name: delta_or_value}
    vars: dict[str, Any] = field(default_factory=dict)
    # 턴 증가
    turn_increment: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "npc_stats": self.npc_stats,
            "flags": self.flags,
            "inventory_add": self.inventory_add,
            "inventory_remove": self.inventory_remove,
            "locks": self.locks,
            "vars": self.vars,
            "turn_increment": self.turn_increment
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateDelta:
        return cls(
            npc_stats=data.get("npc_stats", {}),
            flags=data.get("flags", {}),
            inventory_add=data.get("inventory_add", []),
            inventory_remove=data.get("inventory_remove", []),
            locks=data.get("locks", {}),
            vars=data.get("vars", {}),
            turn_increment=data.get("turn_increment", 0)
        )


def merge_deltas(*deltas: dict[str, Any]) -> dict[str, Any]:
    """여러 델타를 하나로 병합"""
    merged = StateDelta()

    for delta_dict in deltas:
        delta = StateDelta.from_dict(delta_dict) if isinstance(delta_dict, dict) else delta_dict

        # NPC 스탯 병합
        for npc_id, stats in delta.npc_stats.items():
            if npc_id not in merged.npc_stats:
                merged.npc_stats[npc_id] = {}
            for stat, value in stats.items():
                merged.npc_stats[npc_id][stat] = merged.npc_stats[npc_id].get(stat, 0) + value

        # 플래그 병합 (덮어쓰기)
        merged.flags.update(delta.flags)

        # 인벤토리 병합
        merged.inventory_add.extend(delta.inventory_add)
        merged.inventory_remove.extend(delta.inventory_remove)

        # 잠금 병합
        merged.locks.update(delta.locks)

        # 변수 병합 (숫자면 더하기, 아니면 덮어쓰기)
        for key, value in delta.vars.items():
            if key in merged.vars and isinstance(merged.vars[key], (int, float)) and isinstance(value, (int, float)):
                merged.vars[key] += value
            else:
                merged.vars[key] = value

        # 턴 증가 합산
        merged.turn_increment += delta.turn_increment

    return merged.to_dict()
