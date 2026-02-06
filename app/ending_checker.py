"""
app/ending_checker.py
Ending Checker - scenario.yaml의 endings 조건 평가

매 턴 종료 후 실행되어 엔딩 조건을 체크합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas import WorldState
from app.loader import ScenarioAssets
from app.condition_eval import EvalContext, get_condition_evaluator

logger = logging.getLogger(__name__)


class EndingInfo(BaseModel):
    """도달한 엔딩 정보"""
    ending_id: str
    name: str
    epilogue_prompt: str
    on_enter_events: List[Dict[str, Any]] = Field(default_factory=list)


class EndingCheckResult(BaseModel):
    """엔딩 체크 결과"""
    reached: bool
    ending: Optional[EndingInfo] = None
    triggered_delta: Dict[str, Any] = Field(default_factory=dict)


class EndingChecker:
    """
    엔딩 조건 체크

    scenario.yaml의 endings를 순회하며 조건을 평가합니다.
    우선순위는 YAML에 정의된 순서를 따릅니다.
    """

    def __init__(self):
        self._evaluator = get_condition_evaluator()

    def check(
        self,
        world_state: WorldState,
        assets: ScenarioAssets,
    ) -> EndingCheckResult:
        """
        엔딩 조건을 체크하고 결과를 반환합니다.

        Args:
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            EndingCheckResult: 엔딩 체크 결과
        """
        endings = assets.scenario.get("endings", [])
        turn_limit = assets.get_turn_limit()

        # 평가 컨텍스트 생성
        context = EvalContext(
            world_state=world_state,
            turn_limit=turn_limit,
        )

        for ending_def in endings:
            condition = ending_def.get("condition", "")
            if not condition:
                continue

            # 조건 평가
            if self._evaluator.evaluate(condition, context):
                ending_info = EndingInfo(
                    ending_id=ending_def.get("ending_id", ""),
                    name=ending_def.get("name", ""),
                    epilogue_prompt=ending_def.get("epilogue_prompt", ""),
                    on_enter_events=ending_def.get("on_enter_events", []),
                )

                # on_enter_events를 delta로 변환
                triggered_delta = self._events_to_delta(ending_info.on_enter_events)

                logger.info(
                    f"[EndingChecker] 엔딩 도달: {ending_info.ending_id} - {ending_info.name}"
                )

                return EndingCheckResult(
                    reached=True,
                    ending=ending_info,
                    triggered_delta=triggered_delta,
                )

        return EndingCheckResult(reached=False)

    def _events_to_delta(
        self,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        on_enter_events를 state delta로 변환합니다.

        지원하는 이벤트 타입:
        - flag_set: {type: flag_set, key: ending, value: stealth_exit}
        - var_set: {type: var_set, key: some_var, value: 10}
        """
        delta: Dict[str, Any] = {
            "flags": {},
            "vars": {},
        }

        for event in events:
            event_type = event.get("type", "")
            key = event.get("key", "")
            value = event.get("value")

            if event_type == "flag_set":
                delta["flags"][key] = value
            elif event_type == "var_set":
                delta["vars"][key] = value
            else:
                logger.warning(f"[EndingChecker] 알 수 없는 이벤트 타입: {event_type}")

        return delta

    def get_all_endings(
        self,
        assets: ScenarioAssets,
    ) -> List[Dict[str, Any]]:
        """시나리오의 모든 엔딩 정보 반환 (디버그용)"""
        return assets.scenario.get("endings", [])

    def get_victory_conditions(
        self,
        assets: ScenarioAssets,
    ) -> List[str]:
        """승리 조건 반환"""
        return assets.scenario.get("victory_conditions", [])

    def get_failure_conditions(
        self,
        assets: ScenarioAssets,
    ) -> List[str]:
        """실패 조건 반환"""
        return assets.scenario.get("failure_conditions", [])


# ============================================================
# 싱글턴
# ============================================================
_ending_checker_instance: Optional[EndingChecker] = None


def get_ending_checker() -> EndingChecker:
    """EndingChecker 싱글턴 인스턴스 반환"""
    global _ending_checker_instance
    if _ending_checker_instance is None:
        _ending_checker_instance = EndingChecker()
    return _ending_checker_instance


# ============================================================
# 편의 함수
# ============================================================
def check_ending(
    world_state: WorldState,
    assets: ScenarioAssets,
) -> EndingCheckResult:
    """
    엔딩 체크 편의 함수

    Args:
        world_state: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        EndingCheckResult: 엔딩 체크 결과
    """
    checker = get_ending_checker()
    return checker.check(world_state, assets)
