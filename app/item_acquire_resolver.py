"""
app/item_acquire_resolver.py
아이템 획득 리졸버 — 룰 기반 수동 아이템 획득

use(use_type="acquire")로 호출되며,
items.yaml의 acquire.condition을 평가하여 아이템 획득 성공/실패를 판정합니다.
LLM 호출 없이 룰 엔진 기반으로 동작합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.condition_eval import get_condition_evaluator
from app.loader import ScenarioAssets
from app.schemas.condition import EvalContext
from app.schemas.game_state import WorldStatePipeline
from app.schemas.item_use import AcquisitionResult

logger = logging.getLogger(__name__)


class ItemAcquireResolver:
    """
    수동 아이템 획득 리졸버.

    플레이어가 명시적으로 아이템 획득을 시도할 때 사용.
    acquire.condition을 평가하여 성공/실패 + 메시지를 반환합니다.
    """

    def __init__(self) -> None:
        self._evaluator = get_condition_evaluator()

    def resolve(
        self,
        item_id: str,
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
    ) -> Dict[str, Any]:
        """
        아이템 획득을 판정합니다.

        Returns:
            {
                "success": bool,
                "item_id": str,
                "message": str,           # success/failure message
                "acquisition_delta": dict, # 성공 시 inventory_add delta
            }
        """
        # 1. 아이템 정의 확인
        item_def = assets.get_item_by_id(item_id)
        if not item_def:
            logger.info("[ItemAcquireResolver] 존재하지 않는 아이템입니다 !!")
            return {
                "success": False,
                "item_id": item_id,
                "message": f"존재하지 않는 아이템: {item_id}",
                "acquisition_delta": {},
            }

        # 2. 이미 인벤토리에 있는지
        if item_id in world_state.inventory:
            item_name = item_def.get("name", item_id)
            logger.info("[ItemAcquireResolver] 이미 존재하는 아이템입니다 !!")
            return {
                "success": False,
                "item_id": item_id,
                "message": f"이미 {item_name}을(를) 가지고 있다.",
                "acquisition_delta": {},
            }

        acquire = item_def.get("acquire", {})
        item_name = item_def.get("name", item_id)

        # 3. 위치 조건 체크 (acquire.location이 있고, 플레이어 위치가 알려진 경우)
        required_location = acquire.get("location", "")
        if required_location and world_state.player_location:
            if world_state.player_location != required_location:
                failure_msg = acquire.get("failure_message", "") or f"여기서는 {item_name}을(를) 찾을 수 없다."
                logger.info(
                    f"[ItemAcquireResolver] 위치 불일치: item={item_id} "
                    f"required={required_location}, player={world_state.player_location}"
                )
                return {
                    "success": False,
                    "item_id": item_id,
                    "message": failure_msg,
                    "acquisition_delta": {},
                }

        # 4. acquire.condition 평가
        condition = acquire.get("condition", "")
        if condition and condition != "true":
            context = EvalContext(
                world_state=world_state,
                turn_limit=assets.get_turn_limit(),
            )
            if not self._evaluator.evaluate(condition, context):
                failure_msg = acquire.get("failure_message", "")
                logger.info("[ItemAcquireResolver] 현재 조건이 불충족되어 획득이 불가능한 아이템입니다 !!")
                return {
                    "success": False,
                    "item_id": item_id,
                    "message": failure_msg or f"아이템을 획득할 수 없다.",
                    "acquisition_delta": {},
                }

        # 5. 성공
        success_msg = acquire.get("success_message", "")
        if not success_msg:
            success_msg = f"{item_name}을(를) 획득했다."

        delta = {"inventory_add": [item_id]}

        logger.info(f"[ItemAcquireResolver] 획득 성공: {item_id} (condition: {condition})")
        logger.info(f"[ItemAcquireResolver] Location: required={required_location}, player={world_state.player_location}")

        return {
            "success": True,
            "item_id": item_id,
            "message": success_msg,
            "acquisition_delta": delta,
        }


# ============================================================
# 싱글턴
# ============================================================
_instance: Optional[ItemAcquireResolver] = None


def get_item_acquire_resolver() -> ItemAcquireResolver:
    global _instance
    if _instance is None:
        _instance = ItemAcquireResolver()
    return _instance
