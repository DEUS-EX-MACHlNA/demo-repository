"""
app/item_use_resolver.py
아이템 사용 리졸버 — 3단계 트랜잭션 (Validate → Simulate → Commit)

LLM 호출 없이 items.yaml 정의 + 현재 WorldState만으로
아이템 사용의 성공/실패, 효과, 소비 여부를 결정합니다.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from app.condition_eval import get_condition_evaluator
from app.effect_applicator import get_effect_applicator
from app.ending_checker import get_ending_checker
from app.loader import ScenarioAssets
from app.schemas.condition import EvalContext
from app.schemas.game_state import WorldStatePipeline
from app.schemas.item_use import (
    CONSUMABLE_TYPES,
    ItemUseResult,
    StatusEffect,
)
from app.schemas.status import NPCStatus

logger = logging.getLogger(__name__)


class ItemUseResolver:
    """
    아이템 사용 3단계 트랜잭션 리졸버.

    resolve() 한 번 호출로 validate → simulate → commit 전체를 처리.
    모든 판정은 룰 엔진(ConditionEvaluator) 기반, LLM 의존 없음.
    """

    def __init__(self) -> None:
        self._evaluator = get_condition_evaluator()
        self._applicator = get_effect_applicator()
        self._ending_checker = get_ending_checker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        item_id: str,
        action_description: str,
        target_npc_id: Optional[str],
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
    ) -> ItemUseResult:
        """
        아이템 사용을 3단계로 처리합니다.

        Args:
            item_id: 사용할 아이템 ID
            action_description: 플레이어의 행동 서술 (action matching에 활용)
            target_npc_id: 대상 NPC ID (없을 수 있음)
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            ItemUseResult: 성공/실패, state_delta, status_effects 등
        """
        # Step 1: Validate
        validation = self._validate(
            item_id, action_description, target_npc_id, world_state, assets
        )
        if not validation["success"]:
            return ItemUseResult(
                success=False,
                item_id=item_id,
                failure_reason=validation["reason"],
            )

        item_def = validation["item_def"]
        matched_action = validation["matched_action"]

        # Step 2: Simulate
        simulation = self._simulate(
            item_id, item_def, matched_action, target_npc_id, world_state, assets
        )
        if not simulation["success"]:
            return ItemUseResult(
                success=False,
                item_id=item_id,
                action_id=matched_action.get("action_id", ""),
                failure_reason=simulation["reason"],
            )

        # Step 3: Commit
        return self._commit(
            item_id, item_def, matched_action, simulation, target_npc_id
        )

    # ------------------------------------------------------------------
    # Step 1: Validate
    # ------------------------------------------------------------------

    def _validate(
        self,
        item_id: str,
        action_description: str,
        target_npc_id: Optional[str],
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
    ) -> Dict[str, Any]:
        """
        유효성 검사:
        1) 아이템 존재 여부
        2) 인벤토리 보유 여부
        3) 액션 매칭
        4) allowed_when 조건 평가
        """
        # 1. 아이템이 시나리오에 정의되어 있는지
        item_def = assets.get_item_by_id(item_id)
        if not item_def:
            return {"success": False, "reason": f"아이템 정의 없음: {item_id}"}

        # 2. 인벤토리에 있는지
        if item_id not in world_state.inventory:
            return {"success": False, "reason": f"인벤토리에 없음: {item_id}"}

        # 3. 액션 매칭
        actions = item_def.get("use", {}).get("actions", [])
        if not actions:
            return {"success": False, "reason": f"사용 가능한 액션 없음: {item_id}"}

        matched_action = self._match_action(
            actions, action_description, target_npc_id, world_state, assets
        )
        if not matched_action:
            return {"success": False, "reason": "조건을 충족하는 액션이 없음"}

        # 4. allowed_when 조건 평가
        allowed_when = matched_action.get("allowed_when", "")
        if allowed_when:
            context = EvalContext(
                world_state=world_state,
                turn_limit=assets.get_turn_limit(),
                extra_vars={"target_npc_id": target_npc_id or ""},
            )
            if not self._evaluator.evaluate(allowed_when, context):
                failure_msg = matched_action.get("failure_message", "")
                return {
                    "success": False,
                    "reason": failure_msg or f"사용 조건 미충족: {allowed_when}",
                }

        return {
            "success": True,
            "item_def": item_def,
            "matched_action": matched_action,
        }

    def _match_action(
        self,
        actions: List[Dict[str, Any]],
        action_description: str,
        target_npc_id: Optional[str],
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
    ) -> Optional[Dict[str, Any]]:
        """
        플레이어의 action 서술에 맞는 action을 매칭.

        전략:
        1) 단일 액션 → 그것 반환
        2) 복수 액션 → allowed_when이 통과하는 첫 번째 반환
        """
        if len(actions) == 1:
            return actions[0]

        context = EvalContext(
            world_state=world_state,
            turn_limit=assets.get_turn_limit(),
            extra_vars={"target_npc_id": target_npc_id or ""},
        )

        for action in actions:
            allowed_when = action.get("allowed_when", "true")
            if self._evaluator.evaluate(allowed_when, context):
                return action

        # 모든 조건 실패 시 첫 번째 반환 (validate에서 allowed_when 재검사)
        return actions[0]

    # ------------------------------------------------------------------
    # Step 2: Simulate
    # ------------------------------------------------------------------

    def _simulate(
        self,
        item_id: str,
        item_def: Dict[str, Any],
        matched_action: Dict[str, Any],
        target_npc_id: Optional[str],
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
    ) -> Dict[str, Any]:
        """
        가상 적용:
        1) deep copy로 가상 상태 생성
        2) 효과를 가상 적용
        3) 충돌/오류 검사
        4) 엔딩 트리거 가능성 확인
        """
        effects = matched_action.get("effects", [])
        if not effects:
            return {
                "success": True,
                "delta": {},
                "status_effects": [],
                "ending_preview": None,
            }

        # 효과를 StateDelta로 변환
        delta, status_effects = self._applicator.apply_effects(
            effects=effects,
            target_npc_id=target_npc_id,
            world_state=world_state,
            current_turn=world_state.turn,
            source_item_id=item_id,
        )

        # 가상 상태에 delta 적용하여 충돌 검사
        virtual_state = copy.deepcopy(world_state)
        self._apply_delta_to_virtual(virtual_state, delta)

        # 엔딩 트리거 가능성 확인
        ending_preview = None
        try:
            ending_result = self._ending_checker.check(virtual_state, assets)
            if ending_result.reached:
                ending_preview = ending_result.to_ending_info_dict()
        except Exception as e:
            logger.warning(f"[ItemUseResolver] 엔딩 체크 실패 (무시): {e}")

        return {
            "success": True,
            "delta": delta,
            "status_effects": status_effects,
            "ending_preview": ending_preview,
        }

    @staticmethod
    def _apply_delta_to_virtual(
        state: WorldStatePipeline, delta: Dict[str, Any]
    ) -> None:
        """가상 상태에 delta를 적용 (시뮬레이션용)"""
        for npc_id, stats in delta.get("npc_stats", {}).items():
            npc = state.npcs.get(npc_id)
            if not npc:
                continue
            for stat, value in stats.items():
                if isinstance(value, (int, float)) and isinstance(npc.stats.get(stat, 0), (int, float)):
                    npc.stats[stat] = max(0, min(100, npc.stats.get(stat, 0) + value))
                else:
                    npc.stats[stat] = value

        for key, value in delta.get("vars", {}).items():
            if isinstance(value, (int, float)) and isinstance(state.vars.get(key, 0), (int, float)):
                state.vars[key] = state.vars.get(key, 0) + value
            else:
                state.vars[key] = value

        state.flags.update(delta.get("flags", {}))

        for item_id in delta.get("inventory_add", []):
            if item_id not in state.inventory:
                state.inventory.append(item_id)

        for item_id in delta.get("inventory_remove", []):
            if item_id in state.inventory:
                state.inventory.remove(item_id)

        for npc_id, new_status in delta.get("npc_status_changes", {}).items():
            npc = state.npcs.get(npc_id)
            if npc:
                try:
                    npc.status = NPCStatus(new_status)
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    # Step 3: Commit
    # ------------------------------------------------------------------

    def _commit(
        self,
        item_id: str,
        item_def: Dict[str, Any],
        matched_action: Dict[str, Any],
        simulation: Dict[str, Any],
        target_npc_id: Optional[str],
    ) -> ItemUseResult:
        """
        최종 커밋: 소비 판정 + 결과 생성.
        실제 state 변경은 하지 않음 (delta를 반환하여 외부에서 적용).
        """
        delta = simulation["delta"]
        status_effects = simulation["status_effects"]
        ending_preview = simulation.get("ending_preview")

        # 소비 판정
        item_type = item_def.get("type", "")
        consumed = item_type in CONSUMABLE_TYPES

        if consumed:
            delta.setdefault("inventory_remove", [])
            if item_id not in delta["inventory_remove"]:
                delta["inventory_remove"].append(item_id)

        action_id = matched_action.get("action_id", "")
        notes = matched_action.get("success_message", "") or matched_action.get("notes", "")
        effects_applied = matched_action.get("effects", [])

        logger.info(
            f"[ItemUseResolver] 커밋 완료: item={item_id}, action={action_id}, "
            f"consumed={consumed}, effects={len(effects_applied)}, "
            f"ending={'YES: ' + ending_preview['ending_id'] if ending_preview else 'no'}"
        )

        return ItemUseResult(
            success=True,
            action_id=action_id,
            item_id=item_id,
            effects_applied=effects_applied,
            state_delta=delta,
            status_effects=status_effects,
            item_consumed=consumed,
            notes=notes,
            ending_info=ending_preview,
        )


# ============================================================
# 싱글턴
# ============================================================
_instance: Optional[ItemUseResolver] = None


def get_item_use_resolver() -> ItemUseResolver:
    global _instance
    if _instance is None:
        _instance = ItemUseResolver()
    return _instance
