"""
app/day_controller.py
Day Phase Controller (ScenarioController)

낮 페이즈에서 사용자 입력을 처리하고 Tool을 실행합니다.
- Tool Calling (LLM이 직접 tool 선택)
- Tool 실행 (interact, action, use)
"""
from __future__ import annotations

import logging
from typing import Optional

from app.loader import ScenarioAssets
from app.schemas import ToolResult, WorldStatePipeline, UserInputSchema

logger = logging.getLogger(__name__)


class DayController:
    """
    낮 페이즈 컨트롤러

    역할:
    - 사용자 입력 처리
    - 의사결정 로그 추적
    - 턴 실행 (tool_calling -> tool_execute -> output)
    """

    def __init__(self):
        """컨트롤러 초기화"""
        self._decision_log: list[dict] = []

    def process(
        self,
        user_input: str | UserInputSchema,
        world_state: WorldStatePipeline,
        assets: ScenarioAssets,
    ) -> ToolResult:
        """
        사용자 입력을 처리합니다 (tool_calling -> tool_execute -> rule_engine).

        Args:
            user_input: 사용자 입력 (str 또는 UserInputSchema)
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            ToolResult: tool 실행 결과 (Rule Engine delta 포함)
        """
        from app.tools import call_tool, TOOLS, _final_values_to_delta
        from app.rule_engine import apply_memory_rules, merge_rule_delta

        # UserInputSchema를 문자열로 변환
        if isinstance(user_input, UserInputSchema):
            user_input_str = user_input.to_combined_string()
        else:
            user_input_str = user_input

        logger.info(f"[DayController] 처리 시작: user_input={user_input_str[:50]}...")

        # 1. Tool Calling: LLM이 tool, args, intent 선택
        tool_selection = call_tool(user_input_str, world_state, assets)
        tool_name = tool_selection["tool_name"]
        tool_args = tool_selection["args"]
        intent = tool_selection.get("intent", "neutral")
        logger.info(f"[DayController] Tool 선택: {tool_name}, intent={intent}, args={tool_args}")

        # 의사결정 로그에 기록 (intent 포함)
        self._decision_log.append({
            "turn": world_state.turn,
            "user_input": user_input_str,
            "tool_selection": tool_selection,
            "intent": intent,
        })

        # 4. Tool 실행
        tool_fn = TOOLS.get(tool_name)
        if tool_fn:
            result = tool_fn(**tool_args)
        else:
            logger.warning(f"[DayController] 알 수 없는 tool: {tool_name}")
            result = TOOLS["action"](action=user_input_str)

        # 5. use() 결과에서 StatusEffect 등록
        if tool_name == "use" and "item_use_result" in result:
            from app.status_effect_manager import get_status_effect_manager
            from app.schemas.item_use import StatusEffect
            sem = get_status_effect_manager()
            for se_data in result["item_use_result"].get("status_effects", []):
                if isinstance(se_data, dict):
                    sem.apply_effect(StatusEffect(**se_data), world_state)
                elif isinstance(se_data, StatusEffect):
                    sem.apply_effect(se_data, world_state)

        # 6. Rule Engine 적용: intent 기반 자동 상태 변화
        active_npc_id = result.get("npc_id")  # interact에서 반환되는 npc_id
        rule_delta = apply_memory_rules(
            intent=intent,
            memory_rules=assets.memory_rules,
            active_npc_id=active_npc_id,
        )
        logger.info(f"[DayController] Rule Engine 적용: intent={intent}, rule_delta={rule_delta}")

        # 7. Tool delta + Rule delta 병합
        merged_delta = merge_rule_delta(result.get("state_delta"), rule_delta)
        logger.info(f"[DayController] Delta 병합 완료: {merged_delta}")

        tool_result = ToolResult(
            event_description=result.get("event_description", []),
            state_delta=merged_delta,
            intent=intent,
            npc_response=result.get("npc_response"),
            npc_id=result.get("npc_id"),
            item_id=result.get("item_id"),
        )

        logger.info(f"[DayController] 처리 완료: event={tool_result.event_description}")
        return tool_result

    @property
    def decision_log(self) -> list[dict]:
        """의사결정 로그 반환"""
        return self._decision_log


# ============================================================
# 싱글턴
# ============================================================
_day_controller_instance: Optional[DayController] = None


def get_day_controller() -> DayController:
    """DayController 싱글턴 인스턴스 반환"""
    global _day_controller_instance
    if _day_controller_instance is None:
        _day_controller_instance = DayController()
    return _day_controller_instance


# 하위 호환성을 위한 별칭
ScenarioController = DayController
get_controller = get_day_controller


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.schemas import WorldStatePipeline, NPCState

    print("=" * 60)
    print("DAY CONTROLLER 테스트")
    print("=" * 60)

    # 에셋 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n[1] 시나리오 로드됨: {assets.scenario.get('title')}")

    # 테스트용 월드 상태 (시나리오 YAML의 stats 구조에 맞춤)
    world = WorldStatePipeline(
        turn=1,
        npcs={
            "stepmother": NPCState(
                npc_id="stepmother",
                stats={"affection": 50, "fear": 80, "humanity": 0}
            ),
            "stepfather": NPCState(
                npc_id="stepfather",
                stats={"affection": 30, "fear": 60, "humanity": 20}
            ),
            "brother": NPCState(
                npc_id="brother",
                stats={"affection": 60, "fear": 40, "humanity": 50}
            ),
        },
        inventory=[],
        vars={"humanity": 100, "suspicion_level": 0}
    )
    print(f"\n[2] 월드 상태 생성: turn={world.turn}, npcs={list(world.npcs.keys())}")

    # 컨트롤러 생성
    controller = get_day_controller()
    print(f"[3] DayController 생성 완료")

    # 테스트 케이스
    test_cases = [
        "엄마에게 단추가 뭐냐고 물어본다",
        "부엌을 둘러본다",
    ]

    print(f"\n[4] process 테스트 ({len(test_cases)}개):")
    print("-" * 60)

    for text in test_cases:
        print(f"\n  입력: \"{text}\"")
        result = controller.process(text, world, assets)
        print(f"    사건: {result.event_description}")
        print(f"    델타: {result.state_delta}")

    print("\n" + "=" * 60)
    print("DAY CONTROLLER 테스트 완료")
    print("=" * 60)
