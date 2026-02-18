"""
app/effect_applicator.py
효과 적용기 — items.yaml effects 배열을 StateDelta로 변환

순수 데이터 변환 모듈. LLM 호출 없음.

지원하는 효과 타입:
- stat_add / stat_sub   → npc_stats
- var_add               → vars (누적)
- set_state             → npc_stats 즉시 + StatusEffect 생성 (duration 있을 때)
- trigger_event         → flags
- set_env               → vars (덮어쓰기)
- unlock_ending         → flags
- change_scene          → next_node
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.game_state import StateDelta, WorldStatePipeline
from app.schemas.item_use import StatusEffect
from app.schemas.status import NPCStatus

logger = logging.getLogger(__name__)


class EffectApplicator:
    """items.yaml effects → StateDelta 변환기"""

    def apply_effects(
        self,
        effects: List[Dict[str, Any]],
        target_npc_id: Optional[str],
        world_state: WorldStatePipeline,
        current_turn: int,
        source_item_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[StatusEffect]]:
        """
        효과 목록을 StateDelta dict + StatusEffect 리스트로 변환.

        Args:
            effects: items.yaml action.effects 배열
            target_npc_id: 동적 타겟 NPC ID (npc.target.* 해석용)
            world_state: 현재 월드 상태 (original_value 조회용)
            current_turn: 현재 턴 (duration 계산용)
            source_item_id: 효과를 발생시킨 아이템 ID

        Returns:
            (delta_dict, [StatusEffect, ...])
        """
        delta: Dict[str, Any] = {
            "npc_stats": {},
            "npc_status_changes": {},
            "flags": {},
            "vars": {},
            "inventory_add": [],
            "inventory_remove": [],
            "turn_increment": 0,
        }
        status_effects: List[StatusEffect] = []

        for effect in effects:
            effect_type = effect.get("type", "")
            try:
                self._apply_single(
                    effect_type, effect, target_npc_id,
                    world_state, current_turn, source_item_id,
                    delta, status_effects,
                )
            except Exception as e:
                logger.error(f"[EffectApplicator] 효과 적용 실패: {effect} → {e}")

        return delta, status_effects

    def _apply_single(
        self,
        effect_type: str,
        effect: Dict[str, Any],
        target_npc_id: Optional[str],
        world_state: WorldStatePipeline,
        current_turn: int,
        source_item_id: Optional[str],
        delta: Dict[str, Any],
        status_effects: List[StatusEffect],
    ) -> None:
        """단일 효과 적용"""

        if effect_type == "stat_add":
            npc_id, stat = self._resolve_npc_target(effect["target"], target_npc_id)
            if npc_id == "_player":
                delta["vars"][stat] = delta["vars"].get(stat, 0) + effect["value"]
            else:
                delta["npc_stats"].setdefault(npc_id, {})
                delta["npc_stats"][npc_id][stat] = (
                    delta["npc_stats"][npc_id].get(stat, 0) + effect["value"]
                )

        elif effect_type == "stat_sub":
            npc_id, stat = self._resolve_npc_target(effect["target"], target_npc_id)
            if npc_id == "_player":
                delta["vars"][stat] = delta["vars"].get(stat, 0) - effect["value"]
            else:
                delta["npc_stats"].setdefault(npc_id, {})
                delta["npc_stats"][npc_id][stat] = (
                    delta["npc_stats"][npc_id].get(stat, 0) - effect["value"]
                )

        elif effect_type == "var_add":
            key = effect["key"]
            delta["vars"][key] = delta["vars"].get(key, 0) + effect["value"]

        elif effect_type == "set_state":
            npc_id, stat = self._resolve_npc_target(effect["target"], target_npc_id)
            value = effect["value"]
            duration = effect.get("duration")

            # _all_npcs 센티넬을 개별 NPC로 확장
            target_ids = (
                list(world_state.npcs.keys())
                if npc_id == "_all_npcs"
                else [npc_id]
            )

            for tid in target_ids:
                if stat == "status":
                    # NPC status enum 변경 (sleeping, deceased 등)
                    delta["npc_status_changes"][tid] = value
                else:
                    # 일반 스탯 세팅
                    delta["npc_stats"].setdefault(tid, {})
                    delta["npc_stats"][tid][stat] = value

                # duration이 있으면 StatusEffect 생성
                if duration and stat == "status":
                    npc_state = world_state.npcs.get(tid)
                    original = npc_state.status.value if npc_state else "alive"

                    status_effects.append(StatusEffect(
                        target_npc_id=tid,
                        applied_status=NPCStatus(value),
                        original_status=NPCStatus(original),
                        expires_at_turn=current_turn + duration,
                        source_item_id=source_item_id,
                    ))

        elif effect_type == "trigger_event":
            event_id = effect["event_id"]
            delta["flags"][event_id] = True

        elif effect_type == "set_env":
            key = effect["key"]
            delta["vars"][key] = effect["value"]

        elif effect_type == "unlock_ending":
            ending_id = effect["ending_id"]
            delta["flags"][f"ending_unlocked_{ending_id}"] = True

        elif effect_type == "change_scene":
            delta["next_node"] = effect["target"]

        else:
            logger.warning(f"[EffectApplicator] 알 수 없는 효과 타입: {effect_type}")

    @staticmethod
    def _resolve_npc_target(
        target_str: str,
        target_npc_id: Optional[str],
    ) -> Tuple[str, str]:
        """
        target 문자열을 (npc_id, stat_name) 튜플로 해석.

        "npc.target.humanity"  → (resolved_target_id, "humanity")
        "npc.brother.affection" → ("brother", "affection")
        "player.humanity"      → ("_player", "humanity")
        """
        parts = target_str.split(".")
        if len(parts) == 3:
            prefix, npc_ref, stat = parts
            if prefix == "npc":
                if npc_ref == "target":
                    return (target_npc_id or "_unknown", stat)
                elif npc_ref == "all":
                    return ("_all_npcs", stat)
                return (npc_ref, stat)
            elif prefix == "player":
                return ("_player", f"{npc_ref}.{stat}")
        elif len(parts) == 2:
            prefix, stat = parts
            if prefix == "player":
                return ("_player", stat)
            return (prefix, stat)

        logger.warning(f"[EffectApplicator] target 해석 실패: {target_str}")
        return ("_unknown", target_str)


# 싱글턴
_instance: Optional[EffectApplicator] = None


def get_effect_applicator() -> EffectApplicator:
    global _instance
    if _instance is None:
        _instance = EffectApplicator()
    return _instance
