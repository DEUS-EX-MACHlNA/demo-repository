"""
app/tools.py
Tool 시스템 통합

낮 페이즈에서 사용자 입력을 처리하는 Tool 함수들과 유틸리티.
- Tool Calling (LLM이 직접 tool 선택)
- Tool 함수들 (interact, action, use)
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from app.loader import ScenarioAssets
from app.models import WorldState
from app.llm import UnifiedLLMEngine

logger = logging.getLogger(__name__)


# ============================================================
# 전역 인스턴스 (싱글턴)
# ============================================================
_llm_instance: Optional[UnifiedLLMEngine] = None


def _get_llm() -> UnifiedLLMEngine:
    """LLM 엔진 싱글턴 반환"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = UnifiedLLMEngine()
    return _llm_instance


# ============================================================
# Tool 컨텍스트 (tool 함수 내에서 접근)
# ============================================================
_tool_context: Dict[str, Any] = {}


def set_tool_context(
    world_state: WorldState,
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
    world_state: WorldState,
    assets: ScenarioAssets,
) -> Dict[str, Any]:
    """
    LLM을 호출하여 적절한 tool과 args를 선택합니다.

    Args:
        user_input: 사용자 입력 텍스트
        world_state: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        {
            "tool_name": "interact" | "action" | "use",
            "args": dict,  # tool에 전달할 인자
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
                "aliases": npc.get("aliases", []),
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
    prompt = f"""당신은 텍스트 어드벤처 게임의 Tool 선택기입니다.
사용자의 입력을 분석하여 적절한 tool과 인자를 선택하세요.

## 사용 가능한 Tools

1. **interact**: NPC와 대화/상호작용
   - target: NPC ID (필수)
   - interact: 대화 내용 (필수)

2. **action**: 일반 행동 (이동, 조사, 관찰 등)
   - action: 행동 내용 (필수)

3. **use**: 아이템 사용
   - item: 아이템 ID (필수)
   - action: 사용 방법 (필수)

## 현재 상황

NPC 목록:
{_format_npc_list(npc_info_list)}

인벤토리:
{_format_inventory(inventory_info)}

## 사용자 입력
"{user_input}"

## 응답 형식
반드시 아래 JSON 형식으로만 응답하세요:
```json
{{
  "tool_name": "interact" | "action" | "use",
  "args": {{ ... }}
}}
```

예시:
- "엄마에게 말을 건다" → {{"tool_name": "interact", "args": {{"target": "button_mother", "interact": "엄마에게 말을 건다"}}}}
- "부엌을 둘러본다" → {{"tool_name": "action", "args": {{"action": "부엌을 둘러본다"}}}}
- "칼을 사용한다" → {{"tool_name": "use", "args": {{"item": "kitchen_knife", "action": "칼을 사용한다"}}}}
"""

    # 4. LLM 호출
    raw_output = llm_engine.generate(prompt)
    logger.debug(f"[call_tool] LLM 응답: {raw_output}")

    # 5. JSON 파싱
    result = _parse_tool_call_response(raw_output, user_input)
    logger.info(f"[call_tool] 선택된 tool: {result['tool_name']}, args={result['args']}")

    return result


def _format_npc_list(npc_info_list: list) -> str:
    """NPC 목록을 포맷팅"""
    if not npc_info_list:
        return "없음"
    lines = []
    for npc in npc_info_list:
        aliases = ", ".join(npc["aliases"]) if npc["aliases"] else "없음"
        lines.append(f"- {npc['name']} (ID: {npc['id']}, 별칭: {aliases})")
    return "\n".join(lines)


def _format_inventory(inventory_info: list) -> str:
    """인벤토리를 포맷팅"""
    if not inventory_info:
        return "없음"
    lines = []
    for item in inventory_info:
        lines.append(f"- {item['name']} (ID: {item['id']})")
    return "\n".join(lines)


def _parse_tool_call_response(raw_output: str, fallback_input: str) -> Dict[str, Any]:
    """
    LLM의 tool call 응답을 파싱합니다.

    Args:
        raw_output: LLM 출력
        fallback_input: 파싱 실패 시 action으로 사용할 입력

    Returns:
        {"tool_name": str, "args": dict}
    """
    # JSON 블록 추출
    json_match = re.search(r'```json\s*(.*?)\s*```', raw_output, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # ```json 없이 JSON만 있는 경우
        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning(f"[call_tool] JSON 파싱 실패, fallback to action: {raw_output[:100]}")
            return {
                "tool_name": "action",
                "args": {"action": fallback_input},
            }

    try:
        data = json.loads(json_str)
        tool_name = data.get("tool_name", "action")
        args = data.get("args", {})

        # 유효성 검사
        if tool_name not in ("interact", "action", "use"):
            logger.warning(f"[call_tool] 알 수 없는 tool: {tool_name}, fallback to action")
            return {
                "tool_name": "action",
                "args": {"action": fallback_input},
            }

        return {"tool_name": tool_name, "args": args}

    except json.JSONDecodeError as e:
        logger.warning(f"[call_tool] JSON 디코드 실패: {e}, fallback to action")
        return {
            "tool_name": "action",
            "args": {"action": fallback_input},
        }


# ============================================================
# Tool 함수들
# ============================================================
def interact(target: str, interact: str) -> Dict[str, Any]:
    """
    NPC와 상호작용합니다. NPC에게 말을 걸거나 질문할 때 사용합니다.

    Args:
        target: 상호작용할 NPC의 ID (예: "button_mother", "button_father")
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

    # 2. 메모리 검색
    retrieved_memories = []
    if npc_state:
        try:
            retrieved_memories = retrieve_memories(
                npc_extras=npc_state.extras,
                query=interact,
                llm=llm_engine,
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


def use(item: str, action: str) -> Dict[str, Any]:
    """
    아이템이나 환경을 사용합니다. 인벤토리에 있는 아이템이나 환경 요소를 활용할 때 호출합니다.

    Args:
        item: 사용할 아이템의 ID (예: "kitchen_knife", "matches")
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
def _final_values_to_delta(
    raw_delta: Dict[str, Any],
    world_state: WorldState,
) -> Dict[str, Any]:
    """
    LLM이 출력한 최종값을 delta(변화량)로 변환합니다.

    LLM은 "trust: 5"처럼 최종값을 출력하는데,
    실제 delta 적용 시에는 현재값과의 차이를 계산해야 합니다.
    """
    result = {}

    # npc_stats 처리
    if "npc_stats" in raw_delta:
        result["npc_stats"] = {}
        for npc_id, stats in raw_delta["npc_stats"].items():
            if npc_id not in world_state.npcs:
                continue
            npc_state = world_state.npcs[npc_id]
            result["npc_stats"][npc_id] = {}
            for stat, final_value in stats.items():
                if hasattr(npc_state, stat):
                    current = getattr(npc_state, stat)
                    # 최종값 - 현재값 = delta
                    result["npc_stats"][npc_id][stat] = final_value - current

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
