"""
app/status_effect_manager.py
지속시간 기반 상태 효과 관리자

set_state(duration=N) 효과로 생성된 StatusEffect를 큐에 보관하고,
매 턴 시작 시 tick()으로 만료된 효과를 해제하여 원래 상태로 복구합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.schemas.game_state import WorldStatePipeline
from app.schemas.item_use import StatusEffect

logger = logging.getLogger(__name__)


class StatusEffectManager:
    """지속시간 기반 상태 효과 큐"""

    def __init__(self) -> None:
        self._effects: List[StatusEffect] = []

    def add_effect(self, effect: StatusEffect) -> None:
        """
        효과를 큐에 추가.
        동일 target+key가 이미 존재하면 priority 비교 후 교체.
        """
        existing = [
            e for e in self._effects
            if e.target_npc_id == effect.target_npc_id
            and e.stat_key == effect.stat_key
        ]
        for e in existing:
            if effect.priority >= e.priority:
                self._effects.remove(e)
                logger.info(
                    f"[StatusEffectManager] 기존 효과 교체: "
                    f"{e.target_npc_id}.{e.stat_key} (priority {e.priority} → {effect.priority})"
                )
            else:
                logger.info(
                    f"[StatusEffectManager] 기존 효과 유지 (우선순위 높음): "
                    f"{e.target_npc_id}.{e.stat_key}"
                )
                return

        self._effects.append(effect)
        logger.info(
            f"[StatusEffectManager] 효과 등록: {effect.target_npc_id}.{effect.stat_key}"
            f"={effect.value}, 만료 턴={effect.expires_at_turn}"
        )

    def tick(self, current_turn: int) -> Dict[str, Any]:
        """
        만료된 효과를 해제하고, 원래 값 복구용 delta dict 반환.

        호출 시점: 매 턴 시작 (DayController.process() 전)

        Returns:
            StateDelta-compatible dict (npc_stats 복구값 포함)
        """
        delta: Dict[str, Any] = {
            "npc_stats": {},
            "turn_increment": 0,
        }

        expired = [e for e in self._effects if current_turn >= e.expires_at_turn]

        for effect in expired:
            delta["npc_stats"].setdefault(effect.target_npc_id, {})
            delta["npc_stats"][effect.target_npc_id][effect.stat_key] = effect.original_value
            logger.info(
                f"[StatusEffectManager] 효과 만료: {effect.target_npc_id}.{effect.stat_key}"
                f" → 복구값={effect.original_value!r}"
            )
            self._effects.remove(effect)

        return delta

    def get_active_effects(self, npc_id: Optional[str] = None) -> List[StatusEffect]:
        """활성 효과 목록 반환"""
        if npc_id:
            return [e for e in self._effects if e.target_npc_id == npc_id]
        return self._effects.copy()

    def has_active_effect(self, npc_id: str, stat_key: str) -> bool:
        """특정 NPC의 특정 효과가 활성 상태인지 확인"""
        return any(
            e.target_npc_id == npc_id and e.stat_key == stat_key
            for e in self._effects
        )

    def clear(self) -> None:
        """모든 효과 초기화 (게임 리셋 시)"""
        self._effects.clear()
        logger.info("[StatusEffectManager] 모든 효과 초기화")


# ============================================================
# 싱글턴
# ============================================================
_instance: Optional[StatusEffectManager] = None


def get_status_effect_manager() -> StatusEffectManager:
    global _instance
    if _instance is None:
        _instance = StatusEffectManager()
    return _instance
