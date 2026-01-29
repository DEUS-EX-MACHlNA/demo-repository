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
        world_state=world_snapshot.model_dump(),
        memory_summary=None,
        assets=assets.export_for_prompt(),  # 선택
    )

    # 2. LLM 호출
    raw_output = llm.generate(prompt)

    # 3. 파싱 (text + state_delta)
    llm_response = parse_response(raw_output)

    # llm_response 예:
    # {
    #   text: "...",
    #   state_delta: {
    #       "npc_stats": {"family": {"trust": -1}},
    #       "vars": {"clue_count": 1}
    #   }
    # }

    return ToolResult(
        text_fragment=llm_response.text,
        state_delta=llm_response.state_delta,
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
