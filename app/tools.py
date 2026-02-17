"""
app/tools.py
Tool 시스템 통합

낮 페이즈에서 사용자 입력을 처리하는 Tool 함수들과 유틸리티.
- Tool Calling (LLM이 직접 tool 선택)
- Tool 함수들 (interact, action, use)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.loader import ScenarioAssets
from app.schemas import WorldStatePipeline
from app.llm import UnifiedLLMEngine, get_llm
from app.llm.prompt import build_tool_call_prompt
from app.llm.response import parse_tool_call_response
from app.postprocess import postprocess_npc_dialogue

logger = logging.getLogger(__name__)


# ============================================================
# 전역 인스턴스 (싱글턴)
# ============================================================
_llm_instance: Optional[UnifiedLLMEngine] = None


def _get_llm() -> UnifiedLLMEngine:
    """LLM 엔진 싱글턴 반환"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm()
    return _llm_instance


# ============================================================
# Tool 컨텍스트 (tool 함수 내에서 접근)
# ============================================================
_tool_context: Dict[str, Any] = {}


def set_tool_context(
    world_state: WorldStatePipeline,
    assets: ScenarioAssets,
    llm_engine: UnifiedLLMEngine,
) -> None:
    """Tool 실행 전 컨텍스트 설정"""
    _tool_context["world_state"] = world_state
    _tool_context["assets"] = assets
    _tool_context["llm_engine"] = llm_engine


def get_tool_context() -> Dict[str, Any]:
    """현재 tool 컨텍스트 반환"""
    return _tool_context


# ============================================================
# Tool Calling (LLM이 직접 tool 선택)
# ============================================================
def call_tool(
    user_input: str,
    world_state: WorldStatePipeline,
    assets: ScenarioAssets,
) -> Dict[str, Any]:
    """
    LLM을 호출하여 적절한 tool, args, intent를 선택합니다.

    Args:
        user_input: 사용자 입력 텍스트
        world_state: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        {
            "tool_name": "interact" | "action" | "use",
            "args": dict,  # tool에 전달할 인자
            "intent": "investigate" | "obey" | "rebel" | "reveal" | "summarize" | "neutral",
        }
    """
    # 1. LLM 엔진 가져오기 및 Tool context 설정
    llm_engine = _get_llm()

    set_tool_context(
        world_state=world_state,
        assets=assets,
        llm_engine=llm_engine,
    )

    # 2. 현재 상황 정보 수집
    npc_ids = assets.get_all_npc_ids()
    npc_info_list = []
    for npc_id in npc_ids:
        npc = assets.get_npc_by_id(npc_id)
        if npc:
            npc_info_list.append({
                "id": npc_id,
                "name": npc.get("name", npc_id),
            })

    inventory_info = []
    for item_id in world_state.inventory:
        item = assets.get_item_by_id(item_id)
        if item:
            inventory_info.append({
                "id": item_id,
                "name": item.get("name", item_id),
            })

    # 3. Tool calling 프롬프트 생성
    prompt = build_tool_call_prompt(
        user_input=user_input,
        npc_info_list=npc_info_list,
        inventory_info=inventory_info,
    )

    # 4. LLM 호출
    raw_output = llm_engine.generate(prompt=prompt)
    logger.debug(f"[call_tool] LLM 응답: {raw_output}")

    # 5. JSON 파싱
    result = parse_tool_call_response(raw_output, user_input)
    logger.info(f"[call_tool] 선택된 tool: {result['tool_name']}, intent: {result.get('intent', 'neutral')}, args={result['args']}")

    return result


# ============================================================
# Tool 함수들
# ============================================================
def interact(target: str, interact: str) -> Dict[str, Any]:
    """
    NPC와 상호작용합니다. NPC에게 말을 걸거나 질문할 때 사용합니다.

    1) NPC 대사 생성 (generate_utterance)
    2) 영향 분석 (_analyze_impact → state_delta + event_description)
    3) 메모리 저장 (store_dialogue_memories)

    Args:
        target: 상호작용할 NPC의 ID (예: "stepmother", "stepfather")
        interact: NPC와 상호작용에 대한 구체적인 서술

    Returns:
        {npc_response, event_description, state_delta, npc_id}
    """
    from app.agents.dialogue import (
        generate_utterance,
        store_dialogue_memories,
    )
    from app.agents.utils import format_persona

    ctx = _tool_context
    world_state = ctx["world_state"]
    assets = ctx["assets"]
    llm_engine = ctx["llm_engine"]

    logger.info(f"interact 호출: target={target}, interact={interact[:50]}...")

    # 1. NPC 정보 조회
    npc_info = assets.get_npc_by_id(target)
    npc_state = world_state.npcs.get(target)

    if not npc_info:
        logger.warning(f"NPC를 찾을 수 없음: {target}")
        return {
            "npc_response": "",
            "event_description": [f"{target}라는 NPC를 찾을 수 없습니다."],
            "state_delta": {},
            "npc_id": target,
        }

    npc_name = npc_info.get("name", target)
    npc_persona = npc_info.get("persona", {})

    # 2. world_snapshot 조립
    world_snapshot = _build_world_snapshot(world_state, assets)

    # 3. NPC 대사 생성 (메모리 검색은 generate_utterance 내부에서 수행)
    npc_response = generate_utterance(
        speaker_id=target,
        speaker_name=npc_name,
        speaker_persona=npc_persona,
        speaker_memory=npc_state.memory if npc_state else {},
        speaker_stats=npc_state.stats if npc_state else {},
        listener_name="플레이어",
        conversation_history=[{"speaker": "플레이어", "text": interact}],
        llm=llm_engine,
        current_turn=world_state.turn,
        world_snapshot=world_snapshot,
    )

    # 3-1. NPC 대사 후처리 (글리치/광기 효과 적용)
    npc_humanity = npc_state.stats.get("humanity", 100) if npc_state else 100
    npc_response = postprocess_npc_dialogue(
        text=npc_response,
        npc_id=target,
        humanity=npc_humanity,
    )
    logger.info(f"NPC 응답: {npc_response[:80]}...")

    # 4. 영향 분석 (state_delta + event_description)
    world_context = {
        "suspicion_level": world_state.vars.get("suspicion_level", 0),
        "player_humanity": world_state.vars.get("humanity", 100),
    }
    impact = _analyze_impact(
        user_input=interact,
        npc_response=npc_response,
        npc_id=target,
        npc_name=npc_name,
        npc_persona=npc_persona,
        assets=assets,
        llm_engine=llm_engine,
        world_context=world_context,
    )

    # 5. 메모리 저장
    if npc_state:
        try:
            store_dialogue_memories(
                npc_id=target,
                npc_name=npc_name,
                other_name="플레이어",
                conversation=[
                    {"speaker": "플레이어", "text": interact},
                    {"speaker": npc_name, "text": npc_response},
                ],
                npc_memory=npc_state.memory,
                persona_summary=format_persona(npc_persona),
                llm=llm_engine,
                current_turn=world_state.turn,
            )
        except Exception as e:
            logger.warning(f"메모리 저장 실패: {e}")

    return {
        "npc_response": npc_response,
        "event_description": impact["event_description"],
        "state_delta": impact["state_delta"],
        "npc_id": target,
    }


def _analyze_impact(
    user_input: str,
    npc_response: str,
    npc_id: str,
    npc_name: str,
    npc_persona: Dict[str, Any],
    assets: ScenarioAssets,
    llm_engine: Any,
    world_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """대화의 영향을 분석하여 state_delta와 event_description을 반환.

    analyze_conversation_impact()를 호출하는 래퍼.
    플레이어 입력 + NPC 응답을 conversation 형식으로 변환하여 전달하고,
    NPC의 stat delta만 추출.
    """
    from app.agents.dialogue import analyze_conversation_impact

    conversation = [
        {"speaker": "플레이어", "text": user_input},
        {"speaker": npc_name, "text": npc_response},
    ]

    stat_names = assets.get_npc_stat_names()

    result = analyze_conversation_impact(
        npc1_id="player",
        npc1_name="플레이어",
        npc1_persona={},
        npc2_id=npc_id,
        npc2_name=npc_name,
        npc2_persona=npc_persona,
        conversation=conversation,
        llm=llm_engine,
        stat_names=stat_names,
        world_context=world_context,
    )

    # NPC의 stat delta만 추출하여 state_delta로 구성
    npc_stats = result.get("npc_stats", {})
    npc_stat_delta = npc_stats.get(npc_id, {})

    return {
        "state_delta": {"npc_stats": {npc_id: npc_stat_delta}} if npc_stat_delta else {},
        "event_description": result.get("event_description", []),
    }


def action(action: str) -> Dict[str, Any]:
    """
    사용자 개인 행동을 수행합니다. 장소 이동, 조사, 관찰 등에 사용합니다.

    Args:
        action: 사용자 개인 행동에 대한 서술 (예: "현장 주변을 조사한다", "부엌칼을 집어든다")

    Returns:
        행동 결과와 상태 변화 (event_description, state_delta)
    """
    from app.llm.prompt import build_action_prompt
    from app.llm.response import parse_response

    ctx = _tool_context
    world_state = ctx["world_state"]
    assets = ctx["assets"]
    llm_engine = ctx["llm_engine"]

    logger.info(f"action 호출: action={action[:50]}...")

    # world_snapshot 생성 (필요한 정보만 추출)
    world_snapshot = _build_world_snapshot(world_state, assets)

    # 프롬프트 생성 (system/user 분리)
    system_prompt, user_prompt = build_action_prompt(
        action=action,
        world_snapshot=world_snapshot,
        npc_context=assets.export_for_prompt(),
        assets=assets,
    )

    # LLM 호출
    raw_output = llm_engine.generate(prompt=user_prompt, system_prompt=system_prompt)
    llm_response = parse_response(raw_output)

    return {
        "event_description": llm_response.event_description,
        "state_delta": llm_response.state_delta,
    }


def use(item: str, action: str, target: str = None) -> Dict[str, Any]:
    """
    아이템을 사용합니다. 룰 엔진 기반으로 판정하고, LLM은 호출하지 않습니다.

    Args:
        item: 사용할 아이템의 ID (예: "industrial_sedative", "mothers_key")
        action: 아이템을 어떻게, 왜 사용했는지에 대한 서술
        target: 대상 NPC ID (선택, 아이템을 NPC에게 사용할 때)

    Returns:
        아이템 사용 결과와 상태 변화 (event_description, state_delta, item_use_result)
    """
    from app.item_use_resolver import get_item_use_resolver

    ctx = _tool_context
    world_state = ctx["world_state"]
    assets = ctx["assets"]

    logger.info(f"use (rule-engine): item={item}, action={action[:50]}..., target={target}")

    resolver = get_item_use_resolver()
    result = resolver.resolve(
        item_id=item,
        action_description=action,
        target_npc_id=target,
        world_state=world_state,
        assets=assets,
    )

    if result.success:
        item_info = assets.get_item_by_id(item)
        item_name = item_info.get("name", item) if item_info else item
        event_description = [f"{item_name}을(를) 사용했다."]
        if result.notes:
            event_description.append(result.notes)
    else:
        event_description = [f"아이템 사용 실패: {result.failure_reason}"]

    return {
        "event_description": event_description,
        "state_delta": result.state_delta,
        "item_id": item,
        "item_use_result": result.model_dump(),
    }


# ============================================================
# Tool 맵 (이름 → 함수)
# ============================================================
TOOLS: Dict[str, callable] = {
    "interact": interact,
    "action": action,
    "use": use,
}


# ============================================================
# 유틸리티 함수
# ============================================================
def _build_world_snapshot(
    world_state: WorldStatePipeline,
    assets: ScenarioAssets,
) -> Dict[str, Any]:
    """Tool 함수에서 공통으로 사용하는 world_snapshot 생성.

    전체 world_state 대신 LLM에 필요한 핵심 정보만 추출한다.
    """
    return {
        "day": world_state.vars.get("day", 1),
        "turn": world_state.turn,
        "suspicion_level": world_state.vars.get("suspicion_level", 0),
        "player_humanity": world_state.vars.get("humanity", 100),
        "flags": {k: v for k, v in world_state.flags.items() if v},
        "node_id": world_state.vars.get("node_id", "unknown"),
        "inventory": world_state.inventory,
        "genre": assets.scenario.get("genre", ""),
        "tone": assets.scenario.get("tone", ""),
    }


def _final_values_to_delta(
    raw_delta: Dict[str, Any],
    world_state: WorldStatePipeline,
) -> Dict[str, Any]:
    """
    LLM이 출력한 최종값을 delta(변화량)로 변환합니다.

    LLM은 "trust: 5"처럼 최종값을 출력하는데,
    실제 delta 적용 시에는 현재값과의 차이를 계산해야 합니다.

    NPCState.stats Dict 기반으로 수정됨.
    """
    result = {}

    # npc_stats 처리 (stats Dict 기반)
    if "npc_stats" in raw_delta:
        result["npc_stats"] = {}
        for npc_id, stats in raw_delta["npc_stats"].items():
            if npc_id not in world_state.npcs:
                continue
            npc_state = world_state.npcs[npc_id]
            result["npc_stats"][npc_id] = {}
            for stat, final_value in stats.items():
                # stats Dict에서 현재값 조회
                current = npc_state.stats.get(stat, 0)
                if isinstance(current, (int, float)) and isinstance(final_value, (int, float)):
                    # 최종값 - 현재값 = delta
                    result["npc_stats"][npc_id][stat] = final_value - current
                else:
                    result["npc_stats"][npc_id][stat] = final_value

    # vars 처리
    if "vars" in raw_delta:
        result["vars"] = {}
        for key, final_value in raw_delta["vars"].items():
            current = world_state.vars.get(key, 0)
            if isinstance(current, (int, float)) and isinstance(final_value, (int, float)):
                result["vars"][key] = final_value - current
            else:
                result["vars"][key] = final_value

    # 기타 필드는 그대로 복사
    for key in raw_delta:
        if key not in ("npc_stats", "vars"):
            result[key] = raw_delta[key]

    return result


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("Tool 시스템 디버그 시작")
    print("=" * 60)

    try:
        # ----------------------------------------------------
        # 더미 객체 생성 (프로젝트 구조에 맞게 수정 가능)
        # ----------------------------------------------------
        from pathlib import Path
        from app.loader import ScenarioAssets, ScenarioLoader
        from app.schemas import WorldStatePipeline

        # load asset
        base_path = Path(__file__).parent.parent / "scenarios"
        # 로더 생성
        loader = ScenarioLoader(base_path)
        scenario_id = 'coraline'
        assets = loader.load(scenario_id)
        
        # load world state
        world_state = WorldStatePipeline()  # 필요 시 수정

        # ----------------------------------------------------
        # 1. call_tool 테스트
        # ----------------------------------------------------
        test_input = "새엄마에게 왜 나를 싫어하냐고 묻는다"

        print(f"\n[TEST] call_tool → 입력: {test_input}")
        result = call_tool(
            user_input=test_input,
            world_state=world_state,
            assets=assets,
        )

        print("[call_tool 결과]")
        print(result)

        # ----------------------------------------------------
        # 2. 실제 Tool 실행 테스트
        # ----------------------------------------------------
        tool_name = result["tool_name"]
        args = result["args"]

        print(f"\n[TEST] 실행할 tool: {tool_name}")
        if tool_name in TOOLS:
            tool_result = TOOLS[tool_name](**args)
            print("[Tool 실행 결과]")
            print(tool_result)
        else:
            print("알 수 없는 tool")

        # ----------------------------------------------------
        # 3. 단독 interact 테스트
        # ----------------------------------------------------
        print("\n[TEST] interact 단독 테스트")
        interact_result = interact(
            target="stepmother",
            interact="왜 나를 미워하세요?"
        )
        print(interact_result)

        # ----------------------------------------------------
        # 4. 단독 action 테스트
        # ----------------------------------------------------
        print("\n[TEST] action 단독 테스트")
        action_result = action("거실을 조심스럽게 조사한다")
        print(action_result)

        # ----------------------------------------------------
        # 5. 단독 use 테스트 (아이템이 존재할 경우)
        # ----------------------------------------------------
        if world_state.inventory:
            test_item = world_state.inventory[0]
            print(f"\n[TEST] use 단독 테스트 → item={test_item}")
            use_result = use(test_item, "위험을 대비해 사용한다")
            print(use_result)
        else:
            print("\n[TEST] 인벤토리가 비어 있어 use 테스트 생략")

    except Exception as e:
        logger.exception("디버그 실행 중 오류 발생")
        print(f"오류 발생: {e}")

    print("\n=== Tool 시스템 디버그 종료 ===")
