"""
app/parser.py
Prompt Parser (Stub 구현)

실제 LLM 호출 대신 규칙 기반으로 intent를 파싱합니다.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.loader import ScenarioAssets
from app.models import Intent, ParsedInput, WorldState

logger = logging.getLogger(__name__)


class PromptParser:
    """
    유저 입력을 파싱하여 ParsedInput을 생성하는 Stub 파서

    실제 구현에서는 LLM을 호출하여 더 정교한 파싱을 수행합니다.
    이 Stub은 키워드 기반의 간단한 규칙으로 동작합니다.
    """

    # 의도 감지를 위한 키워드 패턴
    INTENT_PATTERNS = {
        Intent.LEADING: [
            r"그러니까.*맞(지|죠|잖아)",
            r"분명히",
            r"확실히",
            r"틀림없이",
            r"아닌가요\?",
            r"그렇지\?",
            r"맞지\?",
            r"~인 거야",
            r"~한 거 아니야",
        ],
        Intent.EMPATHIC: [
            r"힘드(시|셨)",
            r"어려우셨",
            r"이해(해요|합니다)",
            r"공감",
            r"그랬군요",
            r"안타깝",
            r"걱정",
            r"위로",
            r"괜찮",
        ],
        Intent.SUMMARIZE: [
            r"정리하면",
            r"요약하면",
            r"결론적으로",
            r"따라서",
            r"즉,",
            r"다시 말해",
            r"종합하면",
            r"확정",
        ],
        Intent.NEUTRAL: [
            r"언제",
            r"어디",
            r"누구",
            r"무엇",
            r"어떻게",
            r"왜",
            r"\?$",
        ],
    }

    # NPC 감지를 위한 키워드
    NPC_KEYWORDS = {
        "family": ["가족", "유가족", "피해자 가족", "유족"],
        "partner": ["동료", "수사관", "파트너"],
        "witness": ["목격자", "증인"],
    }

    # 아이템 감지를 위한 키워드
    ITEM_KEYWORDS = {
        "casefile_brief": ["브리핑", "사건 개요", "브리핑 팩"],
        "call_log": ["통화 기록", "통화 내역", "로그"],
        "pattern_analyzer": ["패턴 분석", "분석기"],
        "audit_access": ["감사 권한", "접근 권한", "토큰"],
        "memo_pad": ["메모", "메모 패드", "요약"],
    }

    def __init__(self):
        """Stub 파서 초기화"""
        # 컴파일된 패턴 캐시
        self._compiled_patterns: dict[Intent, list[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """정규식 패턴 미리 컴파일"""
        for intent, patterns in self.INTENT_PATTERNS.items():
            self._compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def _detect_intent(self, text: str) -> Intent:
        """
        텍스트에서 의도 감지 (Stub: 키워드 기반)

        TODO: 실제 LLM 호출로 대체
        """
        # 우선순위: LEADING > SUMMARIZE > EMPATHIC > NEUTRAL > UNKNOWN
        priority_order = [Intent.LEADING, Intent.SUMMARIZE, Intent.EMPATHIC, Intent.NEUTRAL]

        for intent in priority_order:
            patterns = self._compiled_patterns.get(intent, [])
            for pattern in patterns:
                if pattern.search(text):
                    logger.debug(f"Intent detected: {intent.value} (pattern: {pattern.pattern})")
                    return intent

        return Intent.UNKNOWN

    def _detect_target(
        self,
        text: str,
        assets: ScenarioAssets,
        world_state: WorldState
    ) -> Optional[str]:
        """
        텍스트에서 대상(NPC 또는 아이템) 감지

        TODO: 실제 LLM 호출로 대체
        """
        text_lower = text.lower()

        # NPC 감지
        for npc_id, keywords in self.NPC_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower or keyword in text:
                    # assets에서 NPC 존재 확인
                    if assets.get_npc_by_id(npc_id):
                        logger.debug(f"Target NPC detected: {npc_id}")
                        return npc_id

        # 아이템 감지 (인벤토리에 있는 것만)
        for item_id, keywords in self.ITEM_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower or keyword in text:
                    if item_id in world_state.inventory:
                        logger.debug(f"Target item detected: {item_id}")
                        return item_id

        # 기본값: 첫 번째 NPC (fallback)
        npc_ids = assets.get_all_npc_ids()
        if npc_ids:
            logger.debug(f"No specific target detected, defaulting to: {npc_ids[0]}")
            return npc_ids[0]

        return None

    def _extract_content(self, text: str) -> str:
        """
        원본 텍스트에서 핵심 내용 추출

        TODO: 실제 LLM 호출로 대체
        """
        # Stub: 원본 텍스트를 그대로 반환 (간단한 정제만)
        content = text.strip()
        # 과도한 공백 제거
        content = re.sub(r"\s+", " ", content)
        return content

    def parse(
        self,
        text: str,
        assets: ScenarioAssets,
        world_snapshot: WorldState
    ) -> ParsedInput:
        """
        유저 입력을 파싱하여 ParsedInput 반환

        Args:
            text: 유저 입력 텍스트
            assets: 시나리오 에셋
            world_snapshot: 현재 월드 상태 스냅샷

        Returns:
            ParsedInput: 파싱 결과
        """
        logger.info(f"Parsing input: '{text[:50]}...'")

        intent = self._detect_intent(text)
        target = self._detect_target(text, assets, world_snapshot)
        content = self._extract_content(text)

        parsed = ParsedInput(
            intent=intent.value,
            target=target,
            content=content,
            raw=text
        )

        logger.info(f"Parsed result: intent={parsed.intent}, target={parsed.target}")
        return parsed

    def get_debug_info(self, parsed: ParsedInput) -> dict:
        """파싱 결과에 대한 디버그 정보 반환"""
        return {
            "parser": "stub_keyword_based",
            "intent": parsed.intent,
            "target": parsed.target,
            "content_length": len(parsed.content),
            "raw_length": len(parsed.raw),
        }


# ============================================================
# 모듈 레벨 인스턴스 (싱글턴 패턴)
# ============================================================
_parser_instance: Optional[PromptParser] = None


def get_parser() -> PromptParser:
    """PromptParser 싱글턴 인스턴스 반환"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = PromptParser()
    return _parser_instance


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState

    print("=" * 60)
    print("PARSER 컴포넌트 테스트")
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

    # 테스트용 월드 상태 생성
    world = WorldState(
        turn=1,
        npcs={
            "family": NPCState(npc_id="family", trust=0, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=0, fear=0, suspicion=1),
        },
        inventory=["casefile_brief", "pattern_analyzer", "memo_pad"],
        vars={"clue_count": 0, "identity_match_score": 0, "fabrication_score": 0}
    )
    print(f"[2] 테스트 월드 상태 생성됨")

    # 파서 생성
    parser = PromptParser()

    # 테스트 케이스들
    test_inputs = [
        "피해자 가족에게 그날 무슨 일이 있었는지 물어본다",
        "그러니까 범인은 그 시간에 현장에 있었던 거 맞지?",
        "힘드셨겠네요. 이해합니다.",
        "정리하면, 목격자는 세 명이고 모두 같은 증언을 했다",
        "패턴 분석기를 사용해서 내 질문 패턴을 확인한다",
        "통화 기록을 확인해봐",
    ]

    print(f"\n[3] 파싱 테스트 ({len(test_inputs)}개):")
    print("-" * 60)

    for i, text in enumerate(test_inputs, 1):
        parsed = parser.parse(text, assets, world)
        print(f"\n  입력 {i}: \"{text[:40]}...\"" if len(text) > 40 else f"\n  입력 {i}: \"{text}\"")
        print(f"    → intent: {parsed.intent}")
        print(f"    → target: {parsed.target}")
        print(f"    → content: {parsed.content[:30]}..." if len(parsed.content) > 30 else f"    → content: {parsed.content}")

    print("\n" + "=" * 60)
    print("✅ PARSER 테스트 완료")
    print("=" * 60)
