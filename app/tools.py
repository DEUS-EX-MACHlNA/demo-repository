# app/tools.py
from __future__ import annotations

import logging
import os
import random
from typing import Any, Dict

from app.loader import ScenarioAssets
from app.models import NightResult, ToolResult, WorldState

from app.llm import LLM_Engine, build_prompt, parse_response

logger = logging.getLogger(__name__)

_llm_instance: LLM_Engine | None = None

# @use_cache
def _get_llm() -> LLM_Engine:
    """LLM 엔진 싱글턴"""
    global _llm_instance
    if _llm_instance is None:
        model_name = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")
        _llm_instance = LLM_Engine(model_name=model_name)
    return _llm_instance


def execute_tool(
    tool_name: str,
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets,
) -> ToolResult:
    """
    tool_name에 따라 적절한 tool 실행 후 ToolResult 반환.
    npc_talk, action, item_usage 모두 tool_turn_resolution으로 위임.
    """
    user_input = args.get("content", args.get("raw", ""))
    if not user_input and "npc_id" in args:
        user_input = f"NPC {args.get('npc_id', '')}에게 대화"
    llm = _get_llm()
    return tool_turn_resolution(user_input, world_snapshot, assets, llm)


def _final_values_to_delta(
    state_delta: dict[str, Any], world_snapshot: WorldState
) -> dict[str, Any]:
    """
    LLM이 출력한 최종값(state_delta)을 apply_delta용 델타로 변환.
    변수명은 delta 유지, 값은 final - current로 계산.
    """
    result: dict[str, Any] = {
        "npc_stats": {},
        "flags": {},
        "inventory_add": [],
        "inventory_remove": [],
        "locks": {},
        "vars": {},
        "turn_increment": 0,
    }

    # npc_stats: 최종값 -> 델타
    for npc_id, stats in state_delta.get("npc_stats", {}).items():
        if not isinstance(stats, dict):
            continue
        npc = world_snapshot.npcs.get(npc_id)
        result["npc_stats"][npc_id] = {}
        for stat_name, final_val in stats.items():
            if not isinstance(final_val, (int, float)):
                continue
            current = 0
            if npc and hasattr(npc, stat_name):
                current = getattr(npc, stat_name, 0) or 0
            delta_val = int(final_val) - int(current)
            if delta_val != 0:
                result["npc_stats"][npc_id][stat_name] = delta_val
        if not result["npc_stats"][npc_id]:
            del result["npc_stats"][npc_id]

    # vars: 최종값 -> 델타
    for key, final_val in state_delta.get("vars", {}).items():
        if isinstance(final_val, (int, float)):
            current = world_snapshot.vars.get(key, 0) or 0
            delta_val = int(final_val) - int(current)
            if delta_val != 0:
                result["vars"][key] = delta_val
        else:
            result["vars"][key] = final_val

    # flags, locks 등은 덮어쓰기
    if state_delta.get("flags"):
        result["flags"] = dict(state_delta["flags"])
    if state_delta.get("locks"):
        result["locks"] = dict(state_delta["locks"])

    return result


def tool_turn_resolution(
    user_input: str,
    world_snapshot: WorldState,
    assets: ScenarioAssets,
    llm: LLM_Engine,
) -> ToolResult:
    """
    한 턴의 모든 의사결정을 LLM에 위임한다 (단일 호출).
    - NPC 반응
    - 아이템 효과
    - 상태 변화 제안 (최종값 출력 -> 내부에서 델타로 변환)
    """

    # 1. 통합 프롬프트 구성
    prompt = build_prompt(
        user_input=user_input,
        world_state=world_snapshot.to_dict(),
        memory_summary=None,
        npc_context=assets.export_for_prompt(),
    )

    # 2. LLM 호출
    raw_output = llm.generate(prompt)

    # 3. 파싱 (event_description + state_delta)
    llm_response = parse_response(raw_output)
    event_description: list[str] = llm_response.event_description or []
    state_delta_raw = llm_response.state_delta or {}

    # 4. 최종값 -> 델타 변환 (merge_deltas/apply_delta 호환)
    state_delta = _final_values_to_delta(state_delta_raw, world_snapshot)

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

    # 3. 실제 LLM 모델 로드 (llm/engine.py 참고)
    import os
    model_name = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")
    print(f"\n[3] LLM 로딩 중: {model_name} (환경변수 LLM_MODEL로 변경 가능)")
    llm = LLM_Engine(model_name=model_name)
    print("[3] LLM 로드 완료")

    user_input = "피해자 가족에게 그날 있었던 일을 물어본다"

    # 4. build_prompt 확인
    prompt = build_prompt(
        user_input=user_input,
        world_state=world.to_dict(),
        memory_summary=None,
        npc_context=assets.export_for_prompt(),
    )
    print(f"\n[4] 프롬프트 길이: {len(prompt)}")
    print("[4] 프롬프트 앞 400자:")
    print("-" * 40)
    print(prompt[:400])
    if len(prompt) > 400:
        print("...")
    print("-" * 40)

    # 5. tool_turn_resolution 호출
    print("\n[5] LLM 생성 중...")
    result = tool_turn_resolution(user_input, world, assets, llm)
    print(f"\n[6] ToolResult:")
    print(f"    event_description: {result.event_description!r}")
    print(f"    state_delta: {result.state_delta}")

    print("\n" + "=" * 60)
    print("OK tool_turn_resolution 디버그 완료")
    print("=" * 60)
