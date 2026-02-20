"""
app/ending_checker.py
Ending Checker - scenario.yaml의 endings 조건 평가

매 턴 종료 후 실행되어 엔딩 조건을 체크합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.schemas import WorldStatePipeline
from app.schemas.ending import EndingInfo, EndingCheckResult
from app.schemas.condition import EvalContext
from app.loader import ScenarioAssets
from app.condition_eval import get_condition_evaluator

logger = logging.getLogger(__name__)


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
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
        skip_has_item: bool = False,
    ) -> EndingCheckResult:
        """
        엔딩 조건을 체크하고 결과를 반환합니다.

        Args:
            world_state: 현재 월드 상태
            assets: 시나리오 에셋
            skip_has_item: True이면 has_item() 조건이 포함된 엔딩을 건너뜀.
                매턴 패시브 체크 시 True로 호출하여, 아이템 사용 엔딩이
                단순 보유만으로 트리거되는 것을 방지합니다.

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

            # has_item 조건이 포함된 엔딩은 매턴 패시브 체크에서 스킵
            if skip_has_item and "has_item(" in condition:
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
    ) -> StateDelta:
        """
        on_enter_events를 StateDelta로 변환합니다.

        지원하는 이벤트 타입:
        - flag_set: {type: flag_set, key: ending, value: stealth_exit}
        - var_set: {type: var_set, key: some_var, value: 10}
        """
        flags: Dict[str, Any] = {}
        vars_: Dict[str, Any] = {}

        for event in events:
            event_type = event.get("type", "")
            key = event.get("key", "")
            value = event.get("value")

            if event_type == "flag_set":
                flags[key] = value
            elif event_type == "var_set":
                vars_[key] = value
            else:
                logger.warning(f"[EndingChecker] 알 수 없는 이벤트 타입: {event_type}")

        return StateDelta(flags=flags, vars=vars_, turn_increment=0)

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
    world_state: WorldStatePipeline,
    assets: ScenarioAssets,
    skip_has_item: bool = False,
) -> EndingCheckResult:
    """
    엔딩 체크 편의 함수

    Args:
        world_state: 현재 월드 상태
        assets: 시나리오 에셋
        skip_has_item: True이면 has_item() 조건 포함 엔딩 스킵

    Returns:
        EndingCheckResult: 엔딩 체크 결과
    """
    checker = get_ending_checker()
    return checker.check(world_state, assets, skip_has_item=skip_has_item)


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    import logging
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.schemas import NPCState, WorldStatePipeline

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("ENDING CHECKER 테스트")
    print("=" * 60)

    # 시나리오 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n[1] 시나리오: {assets.scenario.get('title')}")

    # 엔딩 목록 출력
    checker = get_ending_checker()
    endings = checker.get_all_endings(assets)
    print(f"\n[2] 정의된 엔딩 ({len(endings)}개):")
    for i, ending in enumerate(endings, 1):
        print(f"  {i}. {ending.get('ending_id')}: {ending.get('name')}")
        print(f"     조건: {ending.get('condition', 'N/A')}")

    # 테스트 케이스 1: 엔딩 미도달 (초기 상태)
    print(f"\n[3] 테스트 1: 초기 상태 (엔딩 미도달)")
    print("-" * 60)

    world1 = WorldStatePipeline(
        turn=1,
        npcs={
            "stepmother": NPCState(
                npc_id="stepmother",
                stats={"trust": 5, "fear": 0, "suspicion": 3}
            ),
        },
        vars={"humanity": 80, "suspicion_level": 3, "day": 1},
        inventory=[],
    )

    result1 = checker.check(world1, assets)
    print(f"  엔딩 도달: {result1.reached}")
    if result1.reached:
        print(f"  엔딩 ID: {result1.ending.ending_id}")
        print(f"  엔딩명: {result1.ending.name}")
        print(f"  triggered_delta: {result1.triggered_delta.to_dict()}")

    # 테스트 케이스 2: unfinished_doll 엔딩 (humanity <= 0)
    print(f"\n[4] 테스트 2: 불완전한 박제 엔딩 (humanity=0)")
    print("-" * 60)

    world2 = WorldStatePipeline(
        turn=10,
        npcs={
            "stepmother": NPCState(
                npc_id="stepmother",
                stats={"trust": 2, "fear": 8, "suspicion": 9}
            ),
        },
        vars={"humanity": 0, "suspicion_level": 100, "day": 2},
        inventory=[],
    )

    result2 = checker.check(world2, assets)
    print(f"  엔딩 도달: {result2.reached}")
    if result2.reached:
        print(f"  엔딩 ID: {result2.ending.ending_id}")
        print(f"  엔딩명: {result2.ending.name}")
        print(f"  에필로그 프롬프트: {result2.ending.epilogue_prompt[:80]}...")
        print(f"  triggered_delta: {result2.triggered_delta.to_dict()}")

    # 테스트 케이스 3: eternal_dinner 엔딩 (turn == turn_limit and flags.ending == null)
    print(f"\n[5] 테스트 3: 영원한 식사 시간 엔딩 (turn_limit 도달)")
    print("-" * 60)

    turn_limit = assets.get_turn_limit()
    world3 = WorldStatePipeline(
        turn=turn_limit,
        npcs={
            "stepmother": NPCState(
                npc_id="stepmother",
                stats={"trust": 5, "fear": 5, "suspicion": 5}
            ),
        },
        vars={"humanity": 50, "suspicion_level": 50, "day": 5},
        flags={"ending": None},  # ending이 아직 설정되지 않음
    )

    result3 = checker.check(world3, assets)
    print(f"  엔딩 도달: {result3.reached}")
    if result3.reached:
        print(f"  엔딩 ID: {result3.ending.ending_id}")
        print(f"  엔딩명: {result3.ending.name}")
        print(f"  에필로그 프롬프트: {result3.ending.epilogue_prompt[:80]}...")
        print(f"  triggered_delta: {result3.triggered_delta.to_dict()}")

    print("\n" + "=" * 60)
    print("ENDING CHECKER 테스트 완료")
    print("=" * 60)
