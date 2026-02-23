"""
app/effect_applicator.py
효과 적용기 — items.yaml effects 배열을 StateDelta로 변환

순수 데이터 변환 모듈. LLM 호출 없음.

지원하는 효과 타입:
- npc_stat_add / npc_stat_sub → npc_stats (v3)
- stat_add / stat_sub         → npc_stats (v1 하위호환)
- var_add / var_sub            → vars (누적)
- set_state                    → NPC status 변경 + StatusEffect 생성 (duration 있을 때)
- flag_set                     → flags (v3)
- set_env                      → vars (덮어쓰기)
- unlock_ending                → flags
- change_scene                 → next_node
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

        # ── npc_stat_add (v3) / stat_add (v1) ──
        if effect_type in ("npc_stat_add", "stat_add"):
            npc_id, stat = self._resolve_npc_target(effect["target"], target_npc_id)
            if npc_id == "_player":
                delta["vars"][stat] = delta["vars"].get(stat, 0) + effect["value"]
            else:
                delta["npc_stats"].setdefault(npc_id, {})
                delta["npc_stats"][npc_id][stat] = (
                    delta["npc_stats"][npc_id].get(stat, 0) + effect["value"]
                )

        # ── npc_stat_sub (v3) / stat_sub (v1) ──
        elif effect_type in ("npc_stat_sub", "stat_sub"):
            npc_id, stat = self._resolve_npc_target(effect["target"], target_npc_id)
            if npc_id == "_player":
                delta["vars"][stat] = delta["vars"].get(stat, 0) - effect["value"]
            else:
                delta["npc_stats"].setdefault(npc_id, {})
                delta["npc_stats"][npc_id][stat] = (
                    delta["npc_stats"][npc_id].get(stat, 0) - effect["value"]
                )

        # ── var_add ──
        elif effect_type == "var_add":
            key = self._resolve_var_key(effect["key"])
            delta["vars"][key] = delta["vars"].get(key, 0) + effect["value"]

        # ── var_sub (v3) ──
        elif effect_type == "var_sub":
            key = self._resolve_var_key(effect["key"])
            delta["vars"][key] = delta["vars"].get(key, 0) - effect["value"]

        # ── flag_set (v3) ──
        elif effect_type == "flag_set":
            key = effect["key"]
            delta["flags"][key] = effect["value"]

        # ── set_state → NPC status 변경 + StatusEffect ──
        elif effect_type == "set_state":
            npc_id, _stat = self._resolve_npc_target(effect["target"], target_npc_id)
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

        # ── set_env ──
        elif effect_type == "set_env":
            key = effect["key"]
            delta["vars"][key] = effect["value"]

        # ── unlock_ending ──
        elif effect_type == "unlock_ending":
            ending_id = effect["ending_id"]
            delta["flags"][f"ending_unlocked_{ending_id}"] = True

        # ── change_scene ──
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

    @staticmethod
    def _resolve_var_key(key: str) -> str:
        """
        var key에서 'vars.' 접두사를 제거.
        v3 items.yaml은 'vars.humanity' 형태를 사용하지만
        delta["vars"]에는 'humanity'로 저장해야 함.
        """
        if key.startswith("vars."):
            return key[5:]
        return key


# 싱글턴
_instance: Optional[EffectApplicator] = None


def get_effect_applicator() -> EffectApplicator:
    global _instance
    if _instance is None:
        _instance = EffectApplicator()
    return _instance
