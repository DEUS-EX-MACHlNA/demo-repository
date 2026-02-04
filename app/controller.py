"""
app/controller.py
Scenario Controller

게임 세션 관리 및 의사결정 로그 추적.
실제 LLM 호출은 app.tools.tool_turn_resolution()에서 수행합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.loader import ScenarioAssets
from app.models import ToolResult, WorldState

logger = logging.getLogger(__name__)


class ScenarioController:
    """
    시나리오 컨트롤러

    역할:
    - 게임 세션 관리
    - 의사결정 로그 추적
    - 턴 실행 (parsing -> tool_select -> tool -> output)

    실제 LLM 호출은 app.tools.tool_turn_resolution()에서 수행합니다.
    """
    def __init__(self):
        """컨트롤러 초기화"""
        self._decision_log: list[dict] = []

    def execute_turn(
        self,
        user_input: str,
        world_state: WorldState,
        assets: ScenarioAssets,
    ) -> ToolResult:
        """
        한 턴을 실행합니다 (parsing -> tool_select -> tool -> output return).

        Args:
            user_input: 사용자 입력 텍스트
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            ToolResult: tool 실행 결과
        """
        from app.tools import parse_intention, select_tool
        from app.tools.tools_langchain import (
            set_tool_context,
            interact,
            action,
            use,
        )
        from app.tools import _get_llm, _get_langchain_engine

        logger.info(f"[execute_turn] 시작: user_input={user_input[:50]}...")

        # 1. Parsing: 사용자 입력 의도 파악
        parsed_intent = parse_intention(user_input, world_state, assets)
        logger.info(f"[execute_turn] 파싱 결과: {parsed_intent}")

        # 의사결정 로그에 기록
        self._decision_log.append({
            "turn": world_state.turn,
            "user_input": user_input,
            "parsed_intent": parsed_intent,
        })

        # 2. Tool Selection: 적절한 tool과 args 선택
        tool_selection = select_tool(parsed_intent)
        tool_name = tool_selection["tool_name"]
        tool_args = tool_selection["args"]
        logger.info(f"[execute_turn] Tool 선택: {tool_name}, args={tool_args}")

        # 3. Tool Context 설정
        llm_engine = _get_langchain_engine()
        memory_llm = None
        try:
            memory_llm = _get_llm()
        except Exception as e:
            logger.debug(f"메모리 LLM 로드 실패 (무시됨): {e}")

        set_tool_context(
            world_state=world_state,
            assets=assets,
            llm_engine=llm_engine,
            memory_llm=memory_llm,
        )

        # 4. Tool 실행
        result: dict[str, Any] = {}
        if tool_name == "interact":
            result = interact.invoke(tool_args)
        elif tool_name == "action":
            result = action.invoke(tool_args)
        elif tool_name == "use":
            result = use.invoke(tool_args)
        else:
            logger.warning(f"[execute_turn] 알 수 없는 tool: {tool_name}")
            result = action.invoke({"action": user_input})

        # 5. 결과를 ToolResult로 변환
        from app.tools.tools import _final_values_to_delta

        state_delta = _final_values_to_delta(
            result.get("state_delta", {}),
            world_state
        )

        tool_result = ToolResult(
            event_description=result.get("event_description", []),
            state_delta=state_delta,
        )

        logger.info(f"[execute_turn] 완료: event={tool_result.event_description}")
        return tool_result


# ============================================================
# 모듈 레벨 인스턴스 (싱글턴)
# ============================================================
_controller_instance: Optional[ScenarioController] = None

def get_controller() -> ScenarioController:
    """ScenarioController 싱글턴 인스턴스 반환"""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = ScenarioController()
    return _controller_instance


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState

    print("=" * 60)
    print("CONTROLLER 컴포넌트 테스트")
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

    # 테스트용 월드 상태
    world = WorldState(
        turn=1,
        npcs={
            "family": NPCState(npc_id="family", trust=0, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=0, fear=0, suspicion=1),
            "witness": NPCState(npc_id="witness", trust=0, fear=2, suspicion=0),
        },
        inventory=["casefile_brief", "pattern_analyzer", "memo_pad"],
        vars={"clue_count": 0, "identity_match_score": 0, "fabrication_score": 0}
    )
    print(f"\n[2] 월드 상태 생성: turn={world.turn}, npcs={list(world.npcs.keys())}")

    # 컨트롤러 생성
    controller = get_controller()
    print(f"[3] ScenarioController 생성 완료")

    # 테스트 케이스
    test_cases = [
        "피해자 가족에게 그날 있었던 일을 물어본다",
        "현장 주변을 조사한다",
        "패턴 분석기를 사용한다",
    ]

    print(f"\n[4] execute_turn 테스트 ({len(test_cases)}개):")
    print("-" * 60)

    for text in test_cases:
        print(f"\n  입력: \"{text}\"")
        result = controller.execute_turn(text, world, assets)
        print(f"    사건: {result.event_description}")
        print(f"    델타: {result.state_delta}")

    print("\n" + "=" * 60)
    print("CONTROLLER 테스트 완료")
    print("=" * 60)
