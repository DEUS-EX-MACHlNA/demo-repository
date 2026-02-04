# app/tools.py
from __future__ import annotations

import logging
import os
import random
import time
from typing import Any, Dict

from app.loader import ScenarioAssets
from app.models import NightResult, ToolResult, WorldState

from app.llm import LLM_Engine, build_prompt, parse_response
from app.llm.config import DEFAULT_MODEL

logger = logging.getLogger(__name__)

_llm_instance: LLM_Engine | None = None
_langchain_engine_instance = None


# ============================================================
# Parsing & Tool Selection (규칙 기반, 토큰 제한 없음)
# ============================================================
def parse_intention(
    user_input: str,
    world_state: WorldState,
    assets: ScenarioAssets,
) -> dict[str, Any]:
    """
    사용자 입력을 규칙 기반으로 파싱하여 의도를 파악합니다.

    Args:
        user_input: 사용자 입력 텍스트
        world_state: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        파싱 결과 딕셔너리:
        {
            "intent": "interact" | "use" | "action",
            "target": str | None,  # NPC ID 또는 item ID
            "content": str,  # 정제된 내용
            "raw": str,  # 원본 텍스트
        }
    """
    text = user_input.strip()

    # NPC 목록 가져오기
    npc_ids = assets.get_all_npc_ids()
    npc_names = []
    for npc_id in npc_ids:
        npc_info = assets.get_npc_by_id(npc_id)
        if npc_info:
            npc_names.append(npc_info.get("name", npc_id))

    # 인벤토리 아이템 가져오기
    inventory = world_state.inventory
    item_names = []
    for item_id in inventory:
        item_info = assets.get_item_by_id(item_id)
        if item_info:
            item_names.append(item_info.get("name", item_id))

    # 대화 관련 키워드
    talk_keywords = ["물어", "말", "질문", "대화", "묻", "이야기", "문의", "에게", "한테"]

    # 아이템 사용 관련 키워드
    use_keywords = ["사용", "쓰", "활용", "이용", "적용", "작동"]

    # 1. NPC 대화 감지
    for npc_id, npc_name in zip(npc_ids, npc_names):
        if npc_name in text or npc_id in text:
            # 대화 관련 키워드가 있는지 확인
            has_talk_keyword = any(kw in text for kw in talk_keywords)
            if has_talk_keyword or "에게" in text or "한테" in text:
                return {
                    "intent": "interact",
                    "target": npc_id,
                    "content": text,
                    "raw": user_input,
                }

    # 2. 아이템 사용 감지
    for item_id, item_name in zip(inventory, item_names):
        if item_name in text or item_id in text:
            # 사용 관련 키워드가 있는지 확인
            has_use_keyword = any(kw in text for kw in use_keywords)
            if has_use_keyword:
                return {
                    "intent": "use",
                    "target": item_id,
                    "content": text,
                    "raw": user_input,
                }

    # 3. 일반 행동으로 분류
    return {
        "intent": "action",
        "target": None,
        "content": text,
        "raw": user_input,
    }


def select_tool(
    parsed_intent: dict[str, Any],
) -> dict[str, Any]:
    """
    파싱된 의도를 기반으로 적절한 tool과 args를 선택합니다.

    Args:
        parsed_intent: parse_intention의 반환값

    Returns:
        {
            "tool_name": str,  # "interact" | "action" | "use"
            "args": dict,  # tool에 전달할 인자
        }
    """
    intent = parsed_intent["intent"]
    target = parsed_intent["target"]
    content = parsed_intent["content"]

    if intent == "interact":
        return {
            "tool_name": "interact",
            "args": {
                "target": target,
                "interact": content,
            }
        }
    elif intent == "use":
        return {
            "tool_name": "use",
            "args": {
                "item": target,
                "action": content,
            }
        }
    else:  # action
        return {
            "tool_name": "action",
            "args": {
                "action": content,
            }
        }


def _get_llm() -> LLM_Engine:
    """LLM 엔진 싱글턴 (transformers 기반)"""
    global _llm_instance
    if _llm_instance is None:
        model_name = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        _llm_instance = LLM_Engine(model_name=model_name)
    return _llm_instance


def _get_langchain_engine():
    """LangChain 엔진 싱글턴"""
    global _langchain_engine_instance
    if _langchain_engine_instance is None:
        from app.llm import LangChainEngine
        model = os.environ.get("LANGCHAIN_MODEL", DEFAULT_MODEL)
        _langchain_engine_instance = LangChainEngine(model=model)
    return _langchain_engine_instance


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
    total_start = time.perf_counter()

    # 1. 통합 프롬프트 구성
    # t1_start = time.perf_counter()
    prompt = build_prompt(
        user_input=user_input,
        world_state=world_snapshot.to_dict(),
        memory_summary=None,
        npc_context=assets.export_for_prompt(),
    )
    # t1_end = time.perf_counter()

    # 2. LLM 호출
    # t2_start = time.perf_counter()
    raw_output = llm.generate(prompt)
    # t2_end = time.perf_counter()

    # 3. 파싱 (event_description + state_delta)
    # t3_start = time .perf_counter()
    llm_response = parse_response(raw_output)
    event_description: list[str] = llm_response.event_description or []
    state_delta_raw = llm_response.state_delta or {}
    # t3_end = time.perf_counter()

    # 4. 최종값 -> 델타 변환 (merge_deltas/apply_delta 호환)
    # t4_start = time.perf_counter()
    state_delta = _final_values_to_delta(state_delta_raw, world_snapshot)
    # t4_end = time.perf_counter()

    # total_end = time.perf_counter()

    # 시간 측정 결과 로깅
    # logger.info(
    #     "[tool_turn_resolution] 시간 측정:\n"
    #     f"  1. build_prompt:    {(t1_end - t1_start) * 1000:.2f} ms\n"
    #     f"  2. llm.generate:    {(t2_end - t2_start) * 1000:.2f} ms\n"
    #     f"  3. parse_response:  {(t3_end - t3_start) * 1000:.2f} ms\n"
    #     f"  4. delta_convert:   {(t4_end - t4_start) * 1000:.2f} ms\n"
    #     f"  ──────────────────────────────────\n"
    #     f"  총 소요 시간:       {(total_end - total_start) * 1000:.2f} ms"
    # )

    return ToolResult(
        event_description=event_description,
        state_delta=state_delta,
    )


# ============================================================
# tool_turn_resolution_v2: LangChain bind_tools 기반
# ============================================================
def tool_turn_resolution_v2(
    user_input: str,
    world_snapshot: WorldState,
    assets: ScenarioAssets,
) -> ToolResult:
    """
    LangChain + bind_tools 기반 2단계 턴 해결

    1단계: Router LLM이 의도 분류 (tool 선택)
    2단계: 선택된 tool이 해당 의도의 프롬프트로 응답 생성
    """
    from langchain_core.messages import SystemMessage, HumanMessage

    from app.tools.tools_langchain import (
        AVAILABLE_TOOLS,
        set_tool_context,
        tool_talk,
        tool_action,
        tool_item,
    )

    total_start = time.perf_counter()

    # LLM 엔진 가져오기
    engine = _get_langchain_engine()

    # 사용 중인 모델/빌드 정보 출력
    print("=" * 60)
    print("[tool_turn_resolution_v2] 엔진 정보")
    print(f"  모델: {engine.model}")
    print(f"  base_url: {engine.base_url}")
    print("=" * 60)

    # 메모리 검색용 LLM (optional)
    memory_llm = None
    try:
        from app.llm import get_llm as get_memory_llm
        memory_llm = get_memory_llm()
    except Exception as e:
        logger.debug(f"메모리 LLM 로드 실패 (무시됨): {e}")

    # 1. Tool 컨텍스트 설정
    set_tool_context(
        world_state=world_snapshot,
        assets=assets,
        llm_engine=engine,
        memory_llm=memory_llm,
    )

    # 2. Router LLM 준비 (bind_tools)
    router_llm = engine.get_llm_with_tools(AVAILABLE_TOOLS)

    # 3. Router 시스템 프롬프트
    npc_ids = assets.get_all_npc_ids()
    inventory = world_snapshot.inventory

    router_system = f"""당신은 인터랙티브 노벨 게임의 의도 분류기입니다.
사용자의 입력을 분석하여 적절한 tool을 선택하세요:

- tool_talk: NPC에게 대화하거나 질문하는 경우
- tool_action: 장소 이동, 조사, 관찰 등 일반적인 행동
- tool_item: 아이템을 사용하거나 적용하는 경우

현재 게임 상태:
- NPC 목록: {npc_ids}
- 인벤토리: {inventory}

사용자 입력을 분석하고 적절한 tool을 호출하세요.
"""

    # 4. Router LLM 호출 (Tool Call 결정)
    messages = [
        SystemMessage(content=router_system),
        HumanMessage(content=user_input),
    ]

    logger.info(f"[v2] Router LLM 호출: user_input={user_input[:50]}...")
    router_response = router_llm.invoke(messages)

    # 5. Tool Call 실행
    result: Dict[str, Any] = {}

    if not router_response.tool_calls:
        # Fallback: tool_action으로 처리
        logger.info("[v2] tool_calls 없음, fallback으로 tool_action 사용")
        result = tool_action.invoke({"action_description": user_input})
    else:
        # 첫 번째 tool call 실행
        tc = router_response.tool_calls[0]
        tool_name = tc["name"]
        tool_args = tc["args"]

        logger.info(f"[v2] Tool 선택: {tool_name}, args={tool_args}")

        if tool_name == "tool_talk":
            result = tool_talk.invoke(tool_args)
        elif tool_name == "tool_action":
            result = tool_action.invoke(tool_args)
        elif tool_name == "tool_item":
            result = tool_item.invoke(tool_args)
        else:
            logger.warning(f"[v2] 알 수 없는 tool: {tool_name}, fallback 사용")
            result = tool_action.invoke({"action_description": user_input})

    # 6. 결과를 ToolResult로 변환
    state_delta = _final_values_to_delta(
        result.get("state_delta", {}),
        world_snapshot
    )

    total_end = time.perf_counter()
    elapsed_ms = (total_end - total_start) * 1000
    logger.info(f"[v2] 총 소요 시간: {elapsed_ms:.2f} ms")

    # 결과 요약 출력
    print("=" * 60)
    print("[tool_turn_resolution_v2] 결과 요약")
    print(f"  사용 모델: {engine.model}")
    print(f"  base_url: {engine.base_url}")
    print(f"  소요 시간: {elapsed_ms:.2f} ms")
    print(f"  event_description: {result.get('event_description', [])}")
    print(f"  state_delta: {state_delta}")
    print("=" * 60)

    return ToolResult(
        event_description=result.get("event_description", []),
        state_delta=state_delta,
    )


# ============================================================
# tool_turn_resolution_v2 디버그 (python -m app.tools)
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
    print("tool_turn_resolution_v2 디버그 (LangChain + HuggingFace Router)")
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
    print(f"    inventory: {world.inventory}")

    # 3. 환경변수 확인
    import os
    langchain_model = os.environ.get("LANGCHAIN_MODEL", DEFAULT_MODEL)
    hf_token = os.environ.get("HF_TOKEN", "")
    print(f"\n[3] 환경변수 확인:")
    print(f"    LANGCHAIN_MODEL: {langchain_model}")
    print(f"    HF_TOKEN: {'설정됨' if hf_token else '미설정 (API 호출 실패 가능)'}")

    # 4. 테스트 케이스들
    test_cases = [
        "피해자 가족에게 그날 있었던 일을 물어본다",
        "현장 주변을 조사한다",
        "패턴 분석기를 사용한다",
    ]

    print(f"\n[4] 테스트 케이스 ({len(test_cases)}개)")
    print("-" * 60)

    for i, user_input in enumerate(test_cases, 1):
        print(f"\n>>> 테스트 {i}: \"{user_input}\"")
        print("-" * 40)

        try:
            result = tool_turn_resolution_v2(user_input, world, assets)

            print(f"\n[결과]")
            print(f"  event_description: {result.event_description}")
            print(f"  state_delta: {result.state_delta}")
        except Exception as e:
            print(f"\n[에러] {type(e).__name__}: {e}")

        print("-" * 40)

    print("\n" + "=" * 60)
    print("OK tool_turn_resolution_v2 디버그 완료")
    print("=" * 60)
