# app/tools.py
from __future__ import annotations

import logging
import random
from typing import Any, Dict

from app.loader import ScenarioAssets
from app.models import Intent, NightResult, ToolResult, WorldState

from app.llm import LLM_Engine, build_prompt, parse_response

logger = logging.getLogger(__name__)

# ============================================================
# Tool 1: NPC Talk (state only)
# ============================================================
def tool_1_npc_talk(
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> dict[str, Any]:

    npc_id = args.get("npc_id", "unknown")
    intent = args.get("intent", Intent.NEUTRAL.value)

    state_delta: dict[str, Any] = {"npc_stats": {}, "vars": {}}

    if intent == Intent.LEADING.value:
        state_delta["npc_stats"][npc_id] = {"trust": -1}
        state_delta["vars"]["fabrication_score"] = 1

    elif intent == Intent.EMPATHIC.value:
        state_delta["npc_stats"][npc_id] = {"trust": 1}

    elif intent == Intent.SUMMARIZE.value:
        state_delta["vars"]["clue_count"] = 1
        state_delta["vars"]["identity_match_score"] = 1

    logger.debug(f"tool_1_npc_talk delta={state_delta}")
    return state_delta


# ============================================================
# Tool 2: Action (state only)
# ============================================================
def tool_2_action(
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> dict[str, Any]:

    action_type = args.get("action_type", "observe")
    state_delta: dict[str, Any] = {"vars": {}}

    if action_type == "summarize":
        state_delta["vars"]["clue_count"] = 1
        state_delta["vars"]["fabrication_score"] = 1

    elif action_type == "investigate":
        if random.random() > 0.5:
            state_delta["vars"]["clue_count"] = 1

    logger.debug(f"tool_2_action delta={state_delta}")
    return state_delta


# ============================================================
# Tool 3: Item Usage (state only)
# ============================================================
def tool_3_item_usage(
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> dict[str, Any]:

    item_id = args.get("item_id", "")
    action_id = args.get("action_id", "use")

    item = assets.get_item_by_id(item_id)
    if not item:
        return {}

    actions = item.get("use", {}).get("actions", [])
    action_spec = next(
        (a for a in actions if a.get("action_id") == action_id),
        actions[0] if actions else {}
    )

    state_delta: dict[str, Any] = {"vars": {}}

    for effect in action_spec.get("effects", []):
        if effect.get("type") == "var_add":
            key = effect.get("key", "").replace("vars.", "")
            state_delta["vars"][key] = effect.get("value", 0)

    logger.debug(f"tool_3_item_usage delta={state_delta}")
    return state_delta


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
# Tool Main (Scenario Controller entrypoint)
# ============================================================
def tool_main(
    tool_name: str,
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets,
    llm: LLM_Engine
) -> ToolResult:
    """
    - tool 선택
    - state_delta 계산
    - LLM 1회 호출로 response 생성
    """

    tool_map = {
        "npc_talk": tool_1_npc_talk,
        "action": tool_2_action,
        "item_usage": tool_3_item_usage,
    }

    tool_func = tool_map.get(tool_name)
    if tool_func is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    # 1. 상태 변화 계산
    state_delta = tool_func(args, world_snapshot, assets)

    # 2. 프롬프트 구성
    prompt = build_prompt(
        user_input=args.get("content", ""),
        world_state=world_snapshot.model_dump(),
        memory_summary=None
    )

    # 3. LLM 호출
    raw_output = llm.generate(prompt)
    llm_response = parse_response(raw_output)

    return ToolResult(
        state_delta=state_delta,
        text_fragment=llm_response.text
    )


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState
    from app.llm import LLM_Engine

    print("=" * 60)
    print("TOOLS 컴포넌트 테스트")
    print("=" * 60)

    # 에셋 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("❌ 시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n[1] 시나리오 로드됨: {assets.scenario.get('title')}")

    # 테스트용 월드 상태
    world = WorldState(
        turn=3,
        npcs={
            "family": NPCState(npc_id="family", trust=2, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=1, fear=0, suspicion=2),
            "witness": NPCState(npc_id="witness", trust=0, fear=3, suspicion=1),
        },
        inventory=["casefile_brief", "pattern_analyzer", "memo_pad"],
        vars={
            "clue_count": 2,
            "identity_match_score": 1,
            "fabrication_score": 1
        }
    )

    # LLM 엔진 (실제 테스트 시 mock로 교체 가능)
    llm = LLM_Engine()

    # ========================================================
    # Tool 1: NPC Talk (state only)
    # ========================================================
    print(f"\n[2] Tool 1: NPC Talk (state delta)")
    print("-" * 40)

    intents = ["leading", "empathic", "neutral", "summarize"]
    for intent in intents:
        delta = tool_1_npc_talk(
            {"npc_id": "family", "intent": intent, "content": "테스트"},
            world, assets
        )
        print(f"  intent={intent}")
        print(f"    state_delta: {delta}")

    # ========================================================
    # Tool 2: Action (state only)
    # ========================================================
    print(f"\n[3] Tool 2: Action (state delta)")
    print("-" * 40)

    actions = ["summarize", "investigate", "move", "observe"]
    for action in actions:
        delta = tool_2_action(
            {"action_type": action, "target": None, "content": "테스트"},
            world, assets
        )
        print(f"  action={action}")
        print(f"    state_delta: {delta}")

    # ========================================================
    # Tool 3: Item Usage (state only)
    # ========================================================
    print(f"\n[4] Tool 3: Item Usage (state delta)")
    print("-" * 40)

    for item_id in world.inventory:
        item = assets.get_item_by_id(item_id)
        actions = item.get("use", {}).get("actions", []) if item else []
        action_id = actions[0].get("action_id", "use") if actions else "use"

        delta = tool_3_item_usage(
            {"item_id": item_id, "action_id": action_id, "target": None},
            world, assets
        )
        print(f"  item={item_id}")
        print(f"    state_delta: {delta}")

    # ========================================================
    # Tool Main: Scenario Controller 관점 테스트
    # ========================================================
    print(f"\n[5] tool_main 통합 테스트")
    print("-" * 40)

    result = tool_main(
        tool_name="npc_talk",
        args={
            "npc_id": "family",
            "intent": "leading",
            "content": "당신은 어젯밤 어디에 있었죠?"
        },
        world_snapshot=world,
        assets=assets,
        llm=llm
    )

    print("  ToolResult:")
    print(f"    state_delta: {result.state_delta}")
    print(f"    text_fragment: {result.text_fragment[:80]}...")

    # ========================================================
    # Tool 4: Night Comes
    # ========================================================
    print(f"\n[6] Tool 4: Night Comes 테스트 (3회)")
    print("-" * 40)

    for i in range(3):
        night = tool_4_night_comes(world, assets)
        print(f"  실행 {i + 1}")
        print(f"    is_observed: {night.is_observed}")
        print(f"    night_delta: {night.night_delta}")

    print("\n" + "=" * 60)
    print("✅ TOOLS 테스트 완료")
    print("=" * 60)