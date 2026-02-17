"""
app/status_effect_manager.py
지속시간 기반 NPC status 관리자

set_state(duration=N) 효과로 생성된 StatusEffect를 world_state.flags["status_effects"]에 저장하고,
매 턴 시작 시 tick()으로 만료된 효과를 해제하여 NPC의 status를 원래대로 복구합니다.

주의: stats(숫자 스탯)는 건드리지 않음. status(sleeping, stunned 등)만 관리.
저장소: world_state.flags["status_effects"] (DB에 영속됨)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.schemas.game_state import WorldStatePipeline
from app.schemas.item_use import StatusEffect
from app.schemas.status import NPCStatus

logger = logging.getLogger(__name__)

FLAGS_KEY = "status_effects"


def _load_effects(world_state: WorldStatePipeline) -> List[StatusEffect]:
    """flags에서 StatusEffect 리스트 로드"""
    raw = world_state.flags.get(FLAGS_KEY, [])
    effects = []
    for item in raw:
        if isinstance(item, dict):
            effects.append(StatusEffect(**item))
        elif isinstance(item, StatusEffect):
            effects.append(item)
    return effects


def _save_effects(world_state: WorldStatePipeline, effects: List[StatusEffect]) -> None:
    """StatusEffect 리스트를 flags에 저장"""
    world_state.flags[FLAGS_KEY] = [e.model_dump() for e in effects]


class StatusEffectManager:
    """지속시간 기반 NPC status 효과 관리자 (stateless)

    모든 상태는 world_state.flags["status_effects"]에 저장됩니다.
    NPC의 status 필드만 변경/복구합니다. stats(숫자)는 건드리지 않습니다.
    예: 공업용 수면제 → npc.status = SLEEPING (3턴) → 만료 시 ALIVE 복구
    """

    def apply_effect(
        self,
        effect: StatusEffect,
        world_state: WorldStatePipeline,
    ) -> None:
        """
        효과를 flags에 추가하고 NPC의 status를 즉시 변경.
        동일 NPC에 기존 효과가 있으면 priority 비교 후 교체.
        """
        effects = _load_effects(world_state)

        # 동일 NPC에 대한 기존 효과 확인
        existing = [e for e in effects if e.target_npc_id == effect.target_npc_id]
        for e in existing:
            if effect.priority >= e.priority:
                effects.remove(e)
                logger.info(
                    f"[StatusEffectManager] 기존 효과 교체: "
                    f"{e.target_npc_id} {e.applied_status} → {effect.applied_status}"
                )
            else:
                logger.info(
                    f"[StatusEffectManager] 기존 효과 유지 (우선순위 높음): "
                    f"{e.target_npc_id} {e.applied_status}"
                )
                return

        effects.append(effect)
        _save_effects(world_state, effects)

        # NPC status 즉시 변경
        npc = world_state.npcs.get(effect.target_npc_id)
        if npc:
            npc.status = effect.applied_status
            logger.info(
                f"[StatusEffectManager] 효과 적용: {effect.target_npc_id}.status"
                f" = {effect.applied_status.value}, 만료 턴={effect.expires_at_turn}"
            )

    def tick(self, current_turn: int, world_state: WorldStatePipeline) -> None:
        """
        만료된 효과를 해제하고 NPC의 status를 원래대로 복구.

        호출 시점: 매 턴 시작 (DayController.process() 전)
        """
        effects = _load_effects(world_state)
        expired = [e for e in effects if current_turn >= e.expires_at_turn]

        for effect in expired:
            npc = world_state.npcs.get(effect.target_npc_id)
            if npc:
                npc.status = effect.original_status
                logger.info(
                    f"[StatusEffectManager] 효과 만료: {effect.target_npc_id}.status"
                    f" → {effect.original_status.value} 복구"
                )
            effects.remove(effect)

        _save_effects(world_state, effects)

    def get_active_effects(
        self, world_state: WorldStatePipeline, npc_id: Optional[str] = None
    ) -> List[StatusEffect]:
        """활성 효과 목록 반환"""
        effects = _load_effects(world_state)
        if npc_id:
            return [e for e in effects if e.target_npc_id == npc_id]
        return effects

    def is_status_active(
        self, world_state: WorldStatePipeline, npc_id: str, status: NPCStatus
    ) -> bool:
        """특정 NPC가 특정 status 상태인지 확인"""
        effects = _load_effects(world_state)
        return any(
            e.target_npc_id == npc_id and e.applied_status == status
            for e in effects
        )


# ============================================================
# 싱글턴 (stateless이지만 인터페이스 호환용)
# ============================================================
_instance: Optional[StatusEffectManager] = None


def get_status_effect_manager() -> StatusEffectManager:
    global _instance
    if _instance is None:
        _instance = StatusEffectManager()
    return _instance
