"""
app/controller.py
Scenario Controller

게임 세션 관리 및 의사결정 로그 추적.
실제 LLM 호출은 app.tools.tool_turn_resolution()에서 수행합니다.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ScenarioController:
    """
    시나리오 컨트롤러

    역할:
    - 게임 세션 관리
    - 의사결정 로그 추적

    실제 LLM 호출은 app.tools.tool_turn_resolution()에서 수행합니다.
    """
    def __init__(self):
        """컨트롤러 초기화"""
        self._decision_log: list[dict] = []


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
    from app.tools import tool_turn_resolution
    from app.llm import LLM_Engine
    import os

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

    # LLM 로드
    model_name = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")
    print(f"\n[2] LLM 로딩 중: {model_name}")
    llm = LLM_Engine(model_name=model_name)

    # 테스트 케이스
    test_cases = [
        "피해자 가족에게 그날 있었던 일을 물어본다",
        "패턴 분석기를 사용한다",
    ]

    print(f"\n[3] Tool 테스트 ({len(test_cases)}개):")
    print("-" * 60)

    for text in test_cases:
        result = tool_turn_resolution(text, world, assets, llm)
        print(f"\n  입력: \"{text}\"")
        print(f"    사건: {result.event_description}")
        print(f"    델타: {result.state_delta}")

    print("\n" + "=" * 60)
    print("CONTROLLER 테스트 완료")
    print("=" * 60)
