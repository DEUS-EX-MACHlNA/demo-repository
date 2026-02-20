"""
app/item_acquirer.py
자동 아이템 획득 스캐너

매 액션 종료 후 실행되어, acquire.method가 자동 스캔 대상인 아이템 중
acquire.condition이 충족된 것을 자동으로 인벤토리에 추가합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set

from app.condition_eval import get_condition_evaluator
from app.loader import ScenarioAssets
from app.schemas.condition import EvalContext
from app.schemas.game_state import WorldStatePipeline
from app.schemas.item_use import AcquisitionResult

logger = logging.getLogger(__name__)


class ItemAcquirer:
    """
    자동 아이템 획득 스캐너.

    scan() 호출 시 자동 스캔 대상(auto/unlock/reward) 아이템의
    acquire.condition을 평가하여 조건 충족 + 미보유 + 미획득 아이템을
    자동 인벤토리에 추가합니다.
    """

    def __init__(self) -> None:
        self._evaluator = get_condition_evaluator()
        self._acquired_once: Set[str] = set()

    def scan(
        self,
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
    ) -> AcquisitionResult:
        """
        아이템 획득 조건을 스캔합니다.

        Args:
            world_state: 현재 월드 상태 (delta 적용 후)
            assets: 시나리오 에셋

        Returns:
            AcquisitionResult: 새로 획득한 아이템 목록 + delta
        """
        newly_acquired = []
        items_list = assets.items.get("items", [])

        context = EvalContext(
            world_state=world_state,
            turn_limit=assets.get_turn_limit(),
        )

        for item_def in items_list:
            item_id = item_def.get("item_id", "")
            acquire = item_def.get("acquire", {})
            method = acquire.get("method", "")

            # auto, unlock, reward 메서드만 자동 스캔
            if method not in ("auto", "unlock", "reward"):
                continue

            # 이미 인벤토리에 있음
            if item_id in world_state.inventory:
                continue

            # 이미 한 번 획득한 적 있음 (중복 방지)
            if item_id in self._acquired_once:
                continue

            # 조건 평가
            condition = acquire.get("condition", "")
            if not condition:
                continue

            if self._evaluator.evaluate(condition, context):
                newly_acquired.append(item_id)
                self._acquired_once.add(item_id)
                logger.info(f"[ItemAcquirer] 아이템 획득: {item_id} (조건: {condition})")

        # delta 생성
        delta: Dict[str, Any] = {}
        if newly_acquired:
            delta = {"inventory_add": newly_acquired, "turn_increment": 0}

        return AcquisitionResult(
            newly_acquired=newly_acquired,
            acquisition_delta=delta,
        )

    def reset(self) -> None:
        """획득 이력 초기화 (게임 리셋 시)"""
        self._acquired_once.clear()
        logger.info("[ItemAcquirer] 획득 이력 초기화")


# ============================================================
# 싱글턴
# ============================================================
_instance: Optional[ItemAcquirer] = None


def get_item_acquirer() -> ItemAcquirer:
    global _instance
    if _instance is None:
        _instance = ItemAcquirer()
    return _instance
