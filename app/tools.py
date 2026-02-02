"""
app/tools.py
Tool 구현 (Stub)

실제 LLM 호출 대신 규칙 기반/랜덤 로직으로 동작합니다.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from app.loader import ScenarioAssets
from app.models import Intent, NightResult, ToolResult, WorldState

logger = logging.getLogger(__name__)


# ============================================================
# Tool 1: NPC Talk (대화)
# ============================================================
def tool_1_npc_talk(
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> ToolResult:
    """
    NPC 대화 Tool (Stub)

    Args:
        args: {npc_id, intent, content}
        world_snapshot: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        ToolResult: {state_delta, text_fragment}
    """
    npc_id = args.get("npc_id", "unknown")
    intent = args.get("intent", Intent.NEUTRAL.value)
    content = args.get("content", "")

    logger.info(f"tool_1_npc_talk: npc={npc_id}, intent={intent}")

    # NPC 정보 조회
    npc = assets.get_npc_by_id(npc_id)
    npc_name = npc.get("name", "알 수 없는 인물") if npc else "알 수 없는 인물"

    # Intent에 따른 상태 델타 및 응답 생성
    state_delta: dict[str, Any] = {"npc_stats": {}, "vars": {}}
    text_fragment = ""

    if intent == Intent.LEADING.value:
        # 유도 질문: fabrication_score 증가, trust 감소 가능
        state_delta["npc_stats"][npc_id] = {"trust": -1}
        state_delta["vars"]["fabrication_score"] = 1

        responses = [
            f"{npc_name}이(가) 잠시 망설이다가 고개를 끄덕인다. \"...그렇게 생각하신다면요.\"",
            f"{npc_name}의 눈빛이 흔들린다. \"네, 아마... 그랬을 거예요.\"",
            f"\"...맞아요, 맞는 것 같아요.\" {npc_name}의 대답이 너무 빠르다.",
        ]
        text_fragment = random.choice(responses)

    elif intent == Intent.EMPATHIC.value:
        # 공감: trust 증가
        state_delta["npc_stats"][npc_id] = {"trust": 1}

        responses = [
            f"{npc_name}이(가) 눈물을 훔친다. \"감사합니다... 이해해주셔서.\"",
            f"{npc_name}의 긴장이 조금 풀린다. \"...네, 힘들었어요.\"",
            f"\"처음으로 제 말을 들어주시는 분 같아요.\" {npc_name}이(가) 작게 웃는다.",
        ]
        text_fragment = random.choice(responses)

    elif intent == Intent.SUMMARIZE.value:
        # 요약: clue_count, identity_match_score 증가
        state_delta["vars"]["clue_count"] = 1
        state_delta["vars"]["identity_match_score"] = 1

        responses = [
            f"{npc_name}이(가) 당신의 정리를 듣고 고개를 끄덕인다. \"네, 그 정리가 맞아요.\"",
            f"\"...맞습니다. 정확하게 파악하셨네요.\" 하지만 {npc_name}의 표정이 묘하다.",
            f"{npc_name}이(가) 당신이 정리한 내용을 반복한다. 마치 새로운 기억처럼.",
        ]
        text_fragment = random.choice(responses)

    else:  # NEUTRAL, UNKNOWN
        # 중립 질문: 기본 응답
        responses = [
            f"{npc_name}이(가) 당신의 질문을 곱씹는다. \"글쎄요... 정확히는...\"",
            f"\"기억이 잘...\" {npc_name}이(가) 말끝을 흐린다.",
            f"{npc_name}이(가) 잠시 생각한 뒤 대답한다. \"그건 제가 직접 보진 못했어요.\"",
        ]
        text_fragment = random.choice(responses)

    # 최근 언급 NPC 업데이트
    state_delta["vars"]["last_mentioned_npc_id"] = npc_id

    logger.debug(f"tool_1_npc_talk result: delta={state_delta}")
    return ToolResult(state_delta=state_delta, text_fragment=text_fragment)


# ============================================================
# Tool 2: Action (행동)
# ============================================================
def tool_2_action(
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> ToolResult:
    """
    액션 Tool (Stub)

    Args:
        args: {action_type, target, content}
        world_snapshot: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        ToolResult: {state_delta, text_fragment}
    """
    action_type = args.get("action_type", "observe")
    target = args.get("target")
    content = args.get("content", "")

    logger.info(f"tool_2_action: type={action_type}, target={target}")

    state_delta: dict[str, Any] = {"vars": {}}
    text_fragment = ""

    if action_type == "summarize":
        # 요약 행동: clue_count 증가, fabrication_score 증가
        state_delta["vars"]["clue_count"] = 1
        state_delta["vars"]["fabrication_score"] = 1

        responses = [
            "당신은 지금까지의 진술을 정리한다. 빈틈없는 요약. 하지만 정말 '사실'인가?",
            "메모에 핵심을 기록한다. 논리적으로 완벽하다. 너무 완벽해서 불안하다.",
            "진술들이 하나의 서사로 수렴한다. 당신이 그린 그림대로.",
        ]
        text_fragment = random.choice(responses)

    elif action_type == "investigate":
        # 조사 행동: clue_count 증가 가능성
        if random.random() > 0.5:
            state_delta["vars"]["clue_count"] = 1
            responses = [
                "새로운 세부사항이 눈에 들어온다. 작지만 의미 있는 발견.",
                "놓쳤던 부분을 다시 확인한다. 퍼즐 조각이 하나 더 맞춰진다.",
            ]
        else:
            responses = [
                "더 이상 새로운 건 보이지 않는다. 이미 본 것들뿐.",
                "조사를 계속하지만, 눈에 띄는 건 없다.",
            ]
        text_fragment = random.choice(responses)

    elif action_type == "move":
        # 이동 시도: 이 시나리오에서는 제한됨
        responses = [
            "당신은 AI다. 물리적 이동은 불가능하다.",
            "[시스템] 이동 권한이 없습니다. 질문과 분석만 가능합니다.",
            "화면 속 풍경이 바뀌지 않는다. 당신은 여기서 움직일 수 없다.",
        ]
        text_fragment = random.choice(responses)

    else:  # observe
        # 관찰: 기본 응답
        responses = [
            "주변을 살핀다. 익숙한 장면, 익숙한 침묵.",
            "데이터를 다시 훑는다. 숫자와 기록 사이에 숨겨진 것이 있을까?",
            "모니터 위로 정보가 흐른다. 모든 게 표면적으로는 정상이다.",
        ]
        text_fragment = random.choice(responses)

    logger.debug(f"tool_2_action result: delta={state_delta}")
    return ToolResult(state_delta=state_delta, text_fragment=text_fragment)


# ============================================================
# Tool 3: Item Usage (아이템 사용)
# ============================================================
def tool_3_item_usage(
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> ToolResult:
    """
    아이템 사용 Tool (Stub)

    Args:
        args: {item_id, action_id, target}
        world_snapshot: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        ToolResult: {state_delta, text_fragment}
    """
    item_id = args.get("item_id", "")
    action_id = args.get("action_id", "use")
    target = args.get("target")

    logger.info(f"tool_3_item_usage: item={item_id}, action={action_id}")

    # 아이템 정보 조회
    item = assets.get_item_by_id(item_id)

    if not item:
        logger.warning(f"Item not found: {item_id}")
        return ToolResult(
            state_delta={},
            text_fragment="[시스템] 해당 아이템을 찾을 수 없습니다."
        )

    item_name = item.get("name", "알 수 없는 아이템")

    # 아이템의 actions에서 해당 action 찾기
    actions = item.get("use", {}).get("actions", [])
    action_spec = None
    for act in actions:
        if act.get("action_id") == action_id:
            action_spec = act
            break

    if not action_spec:
        # 첫 번째 액션 사용
        action_spec = actions[0] if actions else {}

    # effects 적용
    state_delta: dict[str, Any] = {"vars": {}}
    effects = action_spec.get("effects", [])

    for effect in effects:
        effect_type = effect.get("type", "")
        key = effect.get("key", "")
        value = effect.get("value", 0)

        if effect_type == "var_add":
            # vars.clue_count 형식에서 실제 키 추출
            var_key = key.replace("vars.", "") if key.startswith("vars.") else key
            state_delta["vars"][var_key] = value

        # TODO: 다른 effect 타입 처리 (npc_stat_add, flag_set 등)

    # 텍스트 생성 (아이템별 커스텀)
    text_templates = {
        "casefile_brief": [
            f"{item_name}을(를) 펼친다. 사건의 윤곽이 다시 선명해진다.",
            "브리핑 자료를 훑는다. 기본에 충실해야 한다.",
        ],
        "call_log": [
            f"{item_name}을(를) 확인한다. 숫자들 사이로 패턴이 보인다.",
            "통화 내역을 대조한다. 시간과 빈도가 무언가를 암시한다.",
        ],
        "pattern_analyzer": [
            f"{item_name}이(가) 작동한다. 당신의 질문 패턴이 시각화된다.",
            "분석기가 결과를 출력한다. 익숙한 리듬이 눈에 띈다.",
        ],
        "audit_access": [
            f"{item_name}을(를) 사용한다. 제한된 영역에 접근이 허용된다.",
            "권한 토큰이 승인된다. 흔적이 로그에 남는다.",
        ],
        "memo_pad": [
            f"{item_name}에 기록한다. 진술이 '사실'로 고정된다.",
            "메모를 정리한다. 당신이 쓴 대로 세계가 정렬된다.",
        ],
    }

    templates = text_templates.get(item_id, [f"{item_name}을(를) 사용했다."])
    text_fragment = random.choice(templates)

    # 최근 사용 아이템 업데이트
    state_delta["vars"]["last_used_item_id"] = item_id

    logger.debug(f"tool_3_item_usage result: delta={state_delta}")
    return ToolResult(state_delta=state_delta, text_fragment=text_fragment)


# ============================================================
# Night Phase — NightController
# ============================================================
# Generative Agents (Park et al. 2023) 기반 Night Phase.
# NPC들이 자율적으로 기억 조회, 성찰, 계획, 대화를 수행한다.
from app.agents.generative_night import NightController, get_night_controller  # noqa: F401


# ============================================================
# Tool Executor (편의 함수)
# ============================================================
def execute_tool(
    tool_name: str,
    args: dict[str, Any],
    world_snapshot: WorldState,
    assets: ScenarioAssets
) -> ToolResult:
    """
    tool_name에 따라 적절한 tool 실행

    Args:
        tool_name: 실행할 tool 이름
        args: tool 인자
        world_snapshot: 현재 월드 상태
        assets: 시나리오 에셋

    Returns:
        ToolResult
    """
    tool_map = {
        "npc_talk": tool_1_npc_talk,
        "action": tool_2_action,
        "item_usage": tool_3_item_usage,
    }

    tool_func = tool_map.get(tool_name)

    if tool_func is None:
        logger.error(f"Unknown tool: {tool_name}, falling back to npc_talk")
        tool_func = tool_1_npc_talk

    return tool_func(args, world_snapshot, assets)


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState

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
        vars={"clue_count": 2, "identity_match_score": 1, "fabrication_score": 1}
    )

    # Tool 1: NPC Talk 테스트
    print(f"\n[2] Tool 1: NPC Talk 테스트")
    print("-" * 40)

    intents = ["leading", "empathic", "neutral", "summarize"]
    for intent in intents:
        result = tool_1_npc_talk(
            {"npc_id": "family", "intent": intent, "content": "테스트"},
            world, assets
        )
        print(f"  intent={intent}:")
        print(f"    delta: {result.state_delta}")
        print(f"    text: {result.text_fragment[:50]}...")

    # Tool 2: Action 테스트
    print(f"\n[3] Tool 2: Action 테스트")
    print("-" * 40)

    actions = ["summarize", "investigate", "move", "observe"]
    for action in actions:
        result = tool_2_action(
            {"action_type": action, "target": None, "content": "테스트"},
            world, assets
        )
        print(f"  action={action}:")
        print(f"    delta: {result.state_delta}")
        print(f"    text: {result.text_fragment[:50]}...")

    # Tool 3: Item Usage 테스트
    print(f"\n[4] Tool 3: Item Usage 테스트")
    print("-" * 40)

    for item_id in world.inventory:
        item = assets.get_item_by_id(item_id)
        actions = item.get("use", {}).get("actions", []) if item else []
        action_id = actions[0].get("action_id", "use") if actions else "use"

        result = tool_3_item_usage(
            {"item_id": item_id, "action_id": action_id, "target": None},
            world, assets
        )
        print(f"  item={item_id}:")
        print(f"    delta: {result.state_delta}")
        print(f"    text: {result.text_fragment[:50]}...")

    # NightController 테스트
    print(f"\n[5] NightController 테스트 (3회 실행)")
    print("-" * 40)

    night_ctrl = NightController()
    for i in range(3):
        result = night_ctrl.run(world, assets)
        print(f"  실행 {i+1}:")
        print(f"    night_delta: {result.night_delta}")
        print(f"    description: {result.night_description[:60]}...")
        print(f"    conversation: {len(result.night_conversation)} rounds")

    print("\n" + "=" * 60)
    print("✅ TOOLS 테스트 완료")
    print("=" * 60)
