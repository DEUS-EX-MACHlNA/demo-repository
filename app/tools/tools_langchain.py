"""
app/tools_langchain.py
LangChain @tool 데코레이터 기반 Tool 함수 정의

2단계 아키텍처에서 각 tool 함수는:
1. 컨텍스트에서 필요한 정보 추출
2. (interact의 경우) 메모리 검색
3. 해당 의도의 프롬프트 빌더 호출
4. LLM 호출
5. 응답 파싱 및 반환
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ============================================================
# 전역 컨텍스트 (tool 함수 내에서 접근)
# ============================================================
_tool_context: Dict[str, Any] = {}


def set_tool_context(
    world_state: Any,  # WorldState
    assets: Any,  # ScenarioAssets
    llm_engine: Any,  # LangChainEngine
    memory_llm: Any = None,  # GenerativeAgentsLLM (optional)
) -> None:
    """Tool 실행 전 컨텍스트 설정"""
    _tool_context["world_state"] = world_state
    _tool_context["assets"] = assets
    _tool_context["llm_engine"] = llm_engine
    _tool_context["memory_llm"] = memory_llm


def get_tool_context() -> Dict[str, Any]:
    """현재 tool 컨텍스트 반환"""
    return _tool_context


# ============================================================
# Tool 함수 정의
# ============================================================
@tool
def interact(target: str, interact: str) -> Dict[str, Any]:
    """
    NPC와 상호작용합니다. NPC에게 말을 걸거나 질문할 때 사용합니다.

    Args:
        target: 상호작용할 NPC의 ID (예: "family", "partner", "witness")
        interact: NPC와 상호작용에 대한 구체적인 서술

    Returns:
        상호작용 결과와 상태 변화 (event_description, state_delta)
    """
    from app.llm.prompt import build_talk_prompt
    from app.llm.response import parse_response
    from app.agents.retrieval import retrieve_memories

    ctx = _tool_context
    world_state = ctx["world_state"]
    assets = ctx["assets"]
    llm_engine = ctx["llm_engine"]
    memory_llm = ctx.get("memory_llm")

    logger.info(f"interact 호출: target={target}, interact={interact[:50]}...")

    # 1. NPC 정보 조회
    npc_info = assets.get_npc_by_id(target)
    npc_state = world_state.npcs.get(target)

    if not npc_info:
        logger.warning(f"NPC를 찾을 수 없음: {target}")
        return {
            "event_description": [f"{target}라는 NPC를 찾을 수 없습니다."],
            "state_delta": {},
            "npc_id": target,
        }

    # 2. 메모리 검색 (interact에서만!)
    retrieved_memories = []
    if memory_llm and npc_state:
        try:
            retrieved_memories = retrieve_memories(
                npc_extras=npc_state.extras,
                query=interact,
                llm=memory_llm,
                current_turn=world_state.turn,
                k=5,
            )
            logger.debug(f"검색된 메모리 수: {len(retrieved_memories)}")
        except Exception as e:
            logger.warning(f"메모리 검색 실패: {e}")

    # 메모리를 dict 형태로 변환
    npc_memory = None
    if retrieved_memories:
        npc_memory = {
            f"memory_{i}": mem.description
            for i, mem in enumerate(retrieved_memories)
        }

    # 3. 프롬프트 생성
    prompt = build_talk_prompt(
        message=interact,
        user_memory=None,
        npc_memory=npc_memory,
        npc_context=assets.export_for_prompt(),
        world_state=world_state.to_dict(),
    )

    # 4. LLM 호출 (응답 생성)
    raw_output = llm_engine.generate(prompt)

    # 5. 파싱 및 반환
    llm_response = parse_response(raw_output)

    return {
        "event_description": llm_response.event_description,
        "state_delta": llm_response.state_delta,
        "npc_id": target,
        "retrieved_memories_count": len(retrieved_memories),
    }


@tool
def action(action: str) -> Dict[str, Any]:
    """
    사용자 개인 행동을 수행합니다. 장소 이동, 조사, 관찰 등에 사용합니다.

    Args:
        action: 사용자 개인 행동에 대한 서술 (예: "현장 주변을 조사한다", "창고로 이동한다")

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

    # 프롬프트 생성
    prompt = build_action_prompt(
        action=action,
        user_state=None,
        world_state=world_state.to_dict(),
        npc_context=assets.export_for_prompt(),
    )

    # LLM 호출
    raw_output = llm_engine.generate(prompt)
    llm_response = parse_response(raw_output)

    return {
        "event_description": llm_response.event_description,
        "state_delta": llm_response.state_delta,
    }


@tool
def use(item: str, action: str) -> Dict[str, Any]:
    """
    아이템이나 환경을 사용합니다. 인벤토리에 있는 아이템이나 환경 요소를 활용할 때 호출합니다.

    Args:
        item: 사용할 아이템의 ID (예: "casefile_brief", "pattern_analyzer")
        action: 아이템이나 환경을 어떻게, 왜 사용했는지에 대한 서술

    Returns:
        아이템 사용 결과와 상태 변화 (event_description, state_delta)
    """
    from app.llm.prompt import build_item_prompt
    from app.llm.response import parse_response

    ctx = _tool_context
    world_state = ctx["world_state"]
    assets = ctx["assets"]
    llm_engine = ctx["llm_engine"]

    logger.info(f"use 호출: item={item}, action={action[:50]}...")

    # 아이템 정보 조회
    item_info = assets.get_item_by_id(item)

    if not item_info:
        logger.warning(f"아이템을 찾을 수 없음: {item}")
        return {
            "event_description": [f"{item}라는 아이템을 찾을 수 없습니다."],
            "state_delta": {},
            "item_id": item,
        }

    # 인벤토리 확인
    if item not in world_state.inventory:
        return {
            "event_description": [f"{item}이(가) 인벤토리에 없습니다."],
            "state_delta": {},
            "item_id": item,
        }

    # 프롬프트 생성
    item_name = item_info.get("name", item)
    prompt = build_item_prompt(
        item_name=item_name,
        item_def=item_info,
        world_state=world_state.to_dict(),
        npc_context=assets.export_for_prompt(),
    )

    # LLM 호출
    raw_output = llm_engine.generate(prompt)
    llm_response = parse_response(raw_output)

    return {
        "event_description": llm_response.event_description,
        "state_delta": llm_response.state_delta,
        "item_id": item,
    }


# ============================================================
# Tool 리스트 (Router에서 bind_tools에 사용)
# ============================================================
AVAILABLE_TOOLS = [interact, action, use]
