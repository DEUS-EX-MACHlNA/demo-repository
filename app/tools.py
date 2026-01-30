# app/tools.py
from __future__ import annotations

import logging
import random
from typing import Any, Dict

from app.loader import ScenarioAssets
from app.models import Intent, NightResult, ToolResult, WorldState

from app.llm import LLM_Engine, build_prompt, parse_response

logger = logging.getLogger(__name__)

def tool_turn_resolution(
    user_input: str,
    world_snapshot: WorldState,
    assets: ScenarioAssets,
    llm: LLM_Engine,
) -> ToolResult:
    """
    한 턴의 모든 의사결정을 LLM에 위임한다.
    - 행동 분류
    - NPC 반응
    - 아이템 효과
    - 상태 변화 제안
    """

    # 1. 프롬프트 구성
    prompt = build_prompt(
        user_input=user_input,
        world_state=world_snapshot.to_dict(),
        memory_summary=None,
        npc_context=assets.export_for_prompt(),
    )

    # 2. LLM 호출
    raw_output = llm.generate(prompt)

    # 3. 파싱 (text + state_delta)
    llm_response = parse_response(raw_output)

    # LLM_Response: cleaned_text 사용; state_delta는 추후 파싱 확장 시 사용
    event_description = llm_response.cleaned_text
    state_delta = getattr(llm_response, "state_delta", None) or {}

    return ToolResult(
        event_description=event_description,
        state_delta=state_delta,
    )
# ============================================================
# Tool 4: Night Comes (state only)
# ============================================================
def tool_4_night_comes(
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> NightResult:

    night_delta: dict[str, Any] = {
        "turn_increment": 1,
        "npc_stats": {},
        "vars": {},
    }

    for npc_id, npc_state in world_snapshot.npcs.items():
        suspicion_change = random.choice([-1, 0, 1])
        trust_change = random.choice([-1, 0])

        if suspicion_change or trust_change:
            night_delta["npc_stats"][npc_id] = {}
            if suspicion_change:
                night_delta["npc_stats"][npc_id]["suspicion"] = suspicion_change
            if trust_change:
                night_delta["npc_stats"][npc_id]["trust"] = trust_change

    fabrication_score = world_snapshot.vars.get("fabrication_score", 0)
    observe_probability = min(0.1 + fabrication_score * 0.1, 0.8)
    is_observed = random.random() < observe_probability

    return NightResult(
        night_delta=night_delta,
        night_dialogue="",
        is_observed=is_observed
    )


# ============================================================
# tool_turn_resolution 디버그 (python -m app.tools)
# ============================================================
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # 프로젝트 루트를 path에 추가
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s %(message)s")

    print("=" * 60)
    print("tool_turn_resolution 디버그")
    print("=" * 60)

    # 1. 시나리오 로드
    base_path = root / "scenarios"
    loader = ScenarioLoader(base_path)
    scenario_ids = loader.list_scenarios()
    if not scenario_ids:
        print("[X] 시나리오 없음")
        sys.exit(1)
    scenario_id = scenario_ids[0]
    assets = loader.load(scenario_id)
    print(f"\n[1] 시나리오 로드: {scenario_id}")

    # 2. 테스트용 월드 상태
    world = WorldState(
        turn=1,
        npcs={
            "family": NPCState(npc_id="family", trust=0, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=0, fear=0, suspicion=1),
            "witness": NPCState(npc_id="witness", trust=0, fear=2, suspicion=0),
        },
        inventory=["casefile_brief", "pattern_analyzer"],
        vars={"clue_count": 0, "fabrication_score": 0},
    )
    print(f"[2] WorldState: turn={world.turn}, npcs={list(world.npcs.keys())}")

    # 3. Mock LLM (실제 모델 없이 프롬프트/파싱만 검증)
    class MockLLM:
        def generate(self, prompt: str, **kwargs: Any) -> str:
            # 디버그: 받은 프롬프트 길이만 로깅
            logger.debug("prompt length=%d", len(prompt))
            return "가족은 눈물을 닦으며 말을 이어갔다. \"그날은 정말… 잊을 수가 없어요.\""

    user_input = "피해자 가족에게 그날 있었던 일을 물어본다"
    llm = MockLLM()

    # 4. build_prompt만 먼저 확인 (선택)
    from app.llm import build_prompt
    prompt = build_prompt(
        user_input=user_input,
        world_state=world.to_dict(),
        memory_summary=None,
        npc_context=assets.export_for_prompt(),
    )
    print(f"\n[3] 프롬프트 길이: {len(prompt)}")
    print("[3] 프롬프트 앞 400자:")
    print("-" * 40)
    print(prompt[:400])
    if len(prompt) > 400:
        print("...")
    print("-" * 40)

    # 5. tool_turn_resolution 호출
    result = tool_turn_resolution(user_input, world, assets, llm)
    print(f"\n[4] ToolResult:")
    print(f"    text_fragment: {result.text_fragment!r}")
    print(f"    state_delta: {result.state_delta}")

    print("\n" + "=" * 60)
    print("OK tool_turn_resolution 디버그 완료")
    print("=" * 60)
