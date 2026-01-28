"""
app/controller.py
Scenario Controller (LM Stub)

ParsedInput + world_snapshot + assets를 분석하여
tool_1/2/3 중 하나를 선택하고 호출 사양을 생성합니다.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from app.loader import ScenarioAssets
from app.models import Intent, ParsedInput, ToolCall, ToolName, WorldState

logger = logging.getLogger(__name__)


class ScenarioController:
    """
    시나리오 컨트롤러 (LM Stub)

    역할:
    1. ParsedInput, world_snapshot, assets를 분석
    2. tool_1(npc_talk), tool_2(action), tool_3(item_usage) 중 하나 선택
    3. 선택된 tool 호출에 필요한 인자(call spec) 생성

    실제 구현에서는 LLM을 호출하여 더 정교한 결정을 수행합니다.
    이 Stub은 규칙 기반의 간단한 로직으로 동작합니다.
    """

    # Intent -> Tool 매핑 (기본 규칙)
    INTENT_TOOL_MAP = {
        Intent.LEADING.value: ToolName.NPC_TALK,
        Intent.NEUTRAL.value: ToolName.NPC_TALK,
        Intent.EMPATHIC.value: ToolName.NPC_TALK,
        Intent.SUMMARIZE.value: ToolName.ACTION,
        Intent.UNKNOWN.value: ToolName.NPC_TALK,  # 기본 폴백
    }

    # 아이템 사용 트리거 키워드
    ITEM_USAGE_KEYWORDS = [
        "사용",
        "써",
        "쓰다",
        "활용",
        "확인",
        "검토",
        "분석",
        "열어",
        "읽어",
    ]

    def __init__(self):
        """컨트롤러 초기화"""
        self._decision_log: list[dict] = []

    def _should_use_item(self, parsed: ParsedInput, world_state: WorldState) -> bool:
        """
        아이템 사용 여부 판단

        조건:
        - target이 인벤토리에 있는 아이템일 때
        - 또는 아이템 사용 키워드가 포함되어 있을 때
        """
        # target이 인벤토리 아이템인 경우
        if parsed.target and parsed.target in world_state.inventory:
            return True

        # 키워드 기반 판단
        text_lower = parsed.content.lower()
        for keyword in self.ITEM_USAGE_KEYWORDS:
            if keyword in text_lower or keyword in parsed.content:
                # 인벤토리에 아이템이 있는지 확인
                if world_state.inventory:
                    return True

        return False

    def _select_item(
        self,
        parsed: ParsedInput,
        world_state: WorldState,
        assets: ScenarioAssets
    ) -> Optional[str]:
        """사용할 아이템 선택"""
        # target이 아이템이면 그것 사용
        if parsed.target and parsed.target in world_state.inventory:
            return parsed.target

        # 키워드 기반으로 아이템 추론
        text = parsed.content.lower()
        for item_id in world_state.inventory:
            item = assets.get_item_by_id(item_id)
            if item:
                item_name = item.get("name", "").lower()
                if item_name in text or item_id in text:
                    return item_id

        # 기본값: 첫 번째 아이템
        if world_state.inventory:
            return world_state.inventory[0]

        return None

    def _select_npc(
        self,
        parsed: ParsedInput,
        world_state: WorldState,
        assets: ScenarioAssets
    ) -> str:
        """대화 대상 NPC 선택"""
        # target이 NPC이면 그것 사용
        if parsed.target:
            npc = assets.get_npc_by_id(parsed.target)
            if npc:
                return parsed.target

        # 기본값: 첫 번째 NPC
        npc_ids = assets.get_all_npc_ids()
        if npc_ids:
            return npc_ids[0]

        return "unknown"

    def _select_action_type(
        self,
        parsed: ParsedInput,
        world_state: WorldState,
        assets: ScenarioAssets
    ) -> str:
        """액션 타입 선택 (summarize, investigate, etc.)"""
        intent = parsed.intent

        if intent == Intent.SUMMARIZE.value:
            return "summarize"
        elif "조사" in parsed.content or "확인" in parsed.content:
            return "investigate"
        elif "이동" in parsed.content or "가" in parsed.content:
            return "move"
        else:
            return "observe"

    def decide(
        self,
        parsed: ParsedInput,
        world_snapshot: WorldState,
        assets: ScenarioAssets
    ) -> ToolCall:
        """
        Tool 선택 및 호출 사양 생성

        Args:
            parsed: 파싱된 입력
            world_snapshot: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            ToolCall: 선택된 tool과 인자
        """
        logger.info(f"Deciding tool for intent={parsed.intent}, target={parsed.target}")

        decision_info = {
            "intent": parsed.intent,
            "target": parsed.target,
            "content_preview": parsed.content[:50] if parsed.content else "",
        }

        try:
            # 1. 아이템 사용 여부 우선 체크
            if self._should_use_item(parsed, world_snapshot):
                item_id = self._select_item(parsed, world_snapshot, assets)
                if item_id:
                    item = assets.get_item_by_id(item_id)
                    # 아이템의 가능한 액션 중 첫 번째 선택
                    actions = item.get("use", {}).get("actions", []) if item else []
                    action_id = actions[0].get("action_id", "use") if actions else "use"

                    decision_info["selected_tool"] = ToolName.ITEM_USAGE.value
                    decision_info["reason"] = "item_usage_detected"
                    self._decision_log.append(decision_info)

                    return ToolCall(
                        tool_name=ToolName.ITEM_USAGE.value,
                        args={
                            "item_id": item_id,
                            "action_id": action_id,
                            "target": parsed.target,
                        }
                    )

            # 2. Intent 기반 Tool 선택
            tool_name = self.INTENT_TOOL_MAP.get(
                parsed.intent,
                ToolName.NPC_TALK  # 기본 폴백
            )

            if tool_name == ToolName.NPC_TALK:
                npc_id = self._select_npc(parsed, world_snapshot, assets)
                decision_info["selected_tool"] = ToolName.NPC_TALK.value
                decision_info["reason"] = f"intent_based ({parsed.intent})"
                self._decision_log.append(decision_info)

                return ToolCall(
                    tool_name=ToolName.NPC_TALK.value,
                    args={
                        "npc_id": npc_id,
                        "intent": parsed.intent,
                        "content": parsed.content,
                    }
                )

            elif tool_name == ToolName.ACTION:
                action_type = self._select_action_type(parsed, world_snapshot, assets)
                decision_info["selected_tool"] = ToolName.ACTION.value
                decision_info["reason"] = f"intent_based ({parsed.intent})"
                self._decision_log.append(decision_info)

                return ToolCall(
                    tool_name=ToolName.ACTION.value,
                    args={
                        "action_type": action_type,
                        "target": parsed.target,
                        "content": parsed.content,
                    }
                )

        except Exception as e:
            logger.error(f"Error in decide: {e}")
            decision_info["error"] = str(e)
            decision_info["fallback"] = True

        # 폴백: 기본 NPC 대화
        logger.warning("Falling back to default npc_talk")
        decision_info["selected_tool"] = ToolName.NPC_TALK.value
        decision_info["reason"] = "fallback"
        self._decision_log.append(decision_info)

        npc_ids = assets.get_all_npc_ids()
        default_npc = npc_ids[0] if npc_ids else "unknown"

        return ToolCall(
            tool_name=ToolName.NPC_TALK.value,
            args={
                "npc_id": default_npc,
                "intent": parsed.intent,
                "content": parsed.content,
            }
        )

    def get_debug_info(self) -> dict:
        """디버그 정보 반환"""
        return {
            "controller": "stub_rule_based",
            "recent_decisions": self._decision_log[-5:] if self._decision_log else [],
        }


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
    from app.parser import PromptParser
    from app.models import WorldState, NPCState

    print("=" * 60)
    print("CONTROLLER 컴포넌트 테스트")
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
        turn=1,
        npcs={
            "family": NPCState(npc_id="family", trust=0, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=0, fear=0, suspicion=1),
            "witness": NPCState(npc_id="witness", trust=0, fear=2, suspicion=0),
        },
        inventory=["casefile_brief", "pattern_analyzer", "memo_pad"],
        vars={"clue_count": 0, "identity_match_score": 0, "fabrication_score": 0}
    )

    # 파서 & 컨트롤러
    parser = PromptParser()
    controller = ScenarioController()

    # 테스트 케이스
    test_cases = [
        ("피해자 가족에게 그날 있었던 일을 물어본다", "NPC Talk 예상"),
        ("그러니까 범인은 현장에 있었던 거 맞지?", "NPC Talk (leading)"),
        ("정리하면 목격자는 세 명이었다", "Action (summarize)"),
        ("패턴 분석기를 사용한다", "Item Usage 예상"),
        ("브리핑 팩을 확인해본다", "Item Usage 예상"),
    ]

    print(f"\n[2] Tool 선택 테스트 ({len(test_cases)}개):")
    print("-" * 60)

    for text, expected in test_cases:
        parsed = parser.parse(text, assets, world)
        toolcall = controller.decide(parsed, world, assets)

        print(f"\n  입력: \"{text}\"")
        print(f"    파싱: intent={parsed.intent}, target={parsed.target}")
        print(f"    선택: {toolcall.tool_name}")
        print(f"    인자: {toolcall.args}")
        print(f"    기대: {expected}")

    print(f"\n[3] 컨트롤러 디버그 정보:")
    debug = controller.get_debug_info()
    print(f"    최근 결정 수: {len(debug.get('recent_decisions', []))}")

    print("\n" + "=" * 60)
    print("✅ CONTROLLER 테스트 완료")
    print("=" * 60)
