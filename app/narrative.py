"""
app/narrative.py
Narrative Layer (Stub)

최종 사용자 출력 텍스트를 조립합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.loader import ScenarioAssets
from app.models import WorldState

logger = logging.getLogger(__name__)


class NarrativeLayer:
    """
    내러티브 레이어 (Stub)

    역할:
    - tool 실행 결과(text_fragment)와 night_dialogue를 조합
    - 최종 사용자에게 보여줄 dialogue 생성
    - 월드 상태 변화를 반영한 추가 묘사 (선택적)

    설계 선택:
    - world_after가 필요할 수 있으므로, render는 world_after를 받아서 처리
    - 병렬 실행 시 apply_delta 완료 후 render 호출하는 구조
    """

    def __init__(self):
        """내러티브 레이어 초기화"""
        self._render_log: list[dict[str, Any]] = []

    def render(
        self,
        text_fragment: str,
        night_dialogue: str,
        world_before: WorldState,
        world_after: WorldState,
        assets: ScenarioAssets
    ) -> str:
        """
        최종 dialogue 조립

        Args:
            text_fragment: tool 실행 결과 텍스트
            night_dialogue: night_comes 결과 텍스트
            world_before: 액션 전 월드 상태
            world_after: 액션 후 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: 최종 사용자 출력 텍스트
        """
        logger.info("Rendering narrative")

        parts = []

        # 1. 메인 텍스트 (tool 결과)
        if text_fragment:
            parts.append(text_fragment)

        # 2. 상태 변화 묘사 (선택적)
        state_change_text = self._describe_state_changes(world_before, world_after, assets)
        if state_change_text:
            parts.append(state_change_text)

        # 3. 밤 내러티브
        if night_dialogue:
            parts.append("")  # 빈 줄로 구분
            parts.append("---")
            parts.append(night_dialogue)

        # 4. 턴 정보 (선택적)
        turn_info = self._get_turn_info(world_after, assets)
        if turn_info:
            parts.append("")
            parts.append(turn_info)

        # 5. 엔딩 체크
        ending_text = self._check_ending(world_after, assets)
        if ending_text:
            parts.append("")
            parts.append("===")
            parts.append(ending_text)

        dialogue = "\n".join(parts)

        # 렌더 로그 기록
        self._render_log.append({
            "turn_before": world_before.turn,
            "turn_after": world_after.turn,
            "dialogue_length": len(dialogue),
            "has_ending": ending_text is not None,
        })

        logger.debug(f"Rendered dialogue: {len(dialogue)} chars")
        return dialogue

    def _describe_state_changes(
        self,
        world_before: WorldState,
        world_after: WorldState,
        assets: ScenarioAssets
    ) -> Optional[str]:
        """
        상태 변화를 묘사하는 텍스트 생성 (Stub)

        주요 변화만 간략하게 언급합니다.
        """
        changes = []

        # 변수 변화 체크
        for var_name in ["clue_count", "identity_match_score", "fabrication_score"]:
            before_val = world_before.vars.get(var_name, 0)
            after_val = world_after.vars.get(var_name, 0)
            diff = after_val - before_val

            if diff > 0:
                if var_name == "clue_count":
                    changes.append("새로운 단서가 추가되었다.")
                elif var_name == "identity_match_score":
                    changes.append("무언가 익숙한 패턴이 감지되었다.")
                elif var_name == "fabrication_score":
                    changes.append("세계가 당신의 관점에 맞춰 조정되었다.")

        # NPC 상태 변화 체크 (간략하게)
        for npc_id, npc_after in world_after.npcs.items():
            npc_before = world_before.npcs.get(npc_id)
            if npc_before:
                trust_diff = npc_after.trust - npc_before.trust
                suspicion_diff = npc_after.suspicion - npc_before.suspicion

                npc = assets.get_npc_by_id(npc_id)
                npc_name = npc.get("name", npc_id) if npc else npc_id

                if trust_diff < -2:
                    changes.append(f"{npc_name}의 신뢰가 크게 흔들렸다.")
                elif trust_diff > 2:
                    changes.append(f"{npc_name}이(가) 당신을 더 신뢰하게 되었다.")

                if suspicion_diff > 2:
                    changes.append(f"{npc_name}의 의심이 깊어졌다.")

        if changes:
            return "\n".join(changes)
        return None

    def _get_turn_info(
        self,
        world_after: WorldState,
        assets: ScenarioAssets
    ) -> Optional[str]:
        """턴 정보 텍스트 생성"""
        turn = world_after.turn
        turn_limit = assets.get_turn_limit()
        remaining = turn_limit - turn

        if remaining <= 0:
            return f"[턴 {turn}/{turn_limit}] 시간이 다 되었다."
        elif remaining <= 3:
            return f"[턴 {turn}/{turn_limit}] 남은 시간: {remaining}턴"
        else:
            return f"[턴 {turn}/{turn_limit}]"

    def _check_ending(
        self,
        world_after: WorldState,
        assets: ScenarioAssets
    ) -> Optional[str]:
        """
        엔딩 조건 체크 및 엔딩 텍스트 반환

        TODO: 실제 구현에서는 조건식 파서 필요
        """
        endings = assets.scenario.get("endings", [])
        turn_limit = assets.get_turn_limit()

        identity_score = world_after.vars.get("identity_match_score", 0)
        fabrication_score = world_after.vars.get("fabrication_score", 0)
        turn = world_after.turn

        # 플래그로 이미 엔딩이 설정되었는지 확인
        current_ending = world_after.flags.get("ending")
        if current_ending:
            for ending in endings:
                if ending.get("ending_id") == current_ending:
                    return self._format_ending(ending)

        # 엔딩 조건 체크 (Stub: 간단한 룰 기반)
        for ending in endings:
            ending_id = ending.get("ending_id")
            condition = ending.get("condition", "")

            # 자기 동일성 수용
            if ending_id == "self_confess" and identity_score >= 8:
                return self._format_ending(ending)

            # 대체 범인 조작
            if ending_id == "scapegoat" and fabrication_score >= 6 and identity_score < 8:
                return self._format_ending(ending)

            # 강제 종료
            if ending_id == "forced_shutdown":
                if turn >= turn_limit and identity_score < 8 and fabrication_score < 6:
                    return self._format_ending(ending)

        return None

    def _format_ending(self, ending: dict[str, Any]) -> str:
        """엔딩 텍스트 포맷팅"""
        name = ending.get("name", "엔딩")
        ending_id = ending.get("ending_id", "unknown")
        epilogue_prompt = ending.get("epilogue_prompt", "")

        # Stub: 간단한 엔딩 메시지
        ending_texts = {
            "self_confess": [
                "당신은 마침내 깨달았다.",
                "모든 증거가 한 곳을 가리킨다. 바로 당신 자신을.",
                "수사 AI는 자신의 정체를 마주한다.",
                "",
                f"=== 엔딩: {name} ===",
            ],
            "scapegoat": [
                "사건은 종결되었다.",
                "범인은 체포되었고, 모든 것이 해결된 것처럼 보인다.",
                "하지만 무언가 빠져 있다. 영원히.",
                "",
                f"=== 엔딩: {name} ===",
            ],
            "forced_shutdown": [
                "[경고] 세션 시간 초과",
                "[시스템] 강제 종료 프로토콜 실행",
                "당신의 로그가 저장되지 않은 채 끊긴다.",
                "진실은 미완으로 남았다.",
                "",
                f"=== 엔딩: {name} ===",
            ],
        }

        texts = ending_texts.get(ending_id, [f"=== 엔딩: {name} ==="])
        return "\n".join(texts)

    def get_debug_info(self) -> dict:
        """디버그 정보 반환"""
        return {
            "narrative": "stub_rule_based",
            "recent_renders": self._render_log[-5:] if self._render_log else [],
        }


# ============================================================
# 모듈 레벨 인스턴스 (싱글턴)
# ============================================================
_narrative_instance: Optional[NarrativeLayer] = None


def get_narrative_layer() -> NarrativeLayer:
    """NarrativeLayer 싱글턴 인스턴스 반환"""
    global _narrative_instance
    if _narrative_instance is None:
        _narrative_instance = NarrativeLayer()
    return _narrative_instance


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState

    print("=" * 60)
    print("NARRATIVE 컴포넌트 테스트")
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

    # 내러티브 레이어
    narrative = NarrativeLayer()

    # 테스트 1: 일반 턴
    print(f"\n[2] 일반 턴 렌더링 테스트")
    print("-" * 40)

    world_before = WorldState(
        turn=3,
        npcs={"family": NPCState(npc_id="family", trust=2, fear=0, suspicion=0)},
        vars={"clue_count": 2, "identity_match_score": 2, "fabrication_score": 1}
    )
    world_after = WorldState(
        turn=4,
        npcs={"family": NPCState(npc_id="family", trust=3, fear=0, suspicion=0)},
        vars={"clue_count": 3, "identity_match_score": 3, "fabrication_score": 2}
    )

    dialogue = narrative.render(
        text_fragment="피해자 가족이 고개를 끄덕인다. \"그랬어요...\"",
        night_dialogue="밤이 깊어간다. 진실과 조작의 경계가 흐려진다.",
        world_before=world_before,
        world_after=world_after,
        assets=assets
    )
    print(dialogue)

    # 테스트 2: 엔딩 조건 체크
    print(f"\n[3] 엔딩 조건 테스트 - self_confess")
    print("-" * 40)

    world_ending = WorldState(
        turn=10,
        npcs={"family": NPCState(npc_id="family", trust=5, fear=0, suspicion=0)},
        vars={"clue_count": 5, "identity_match_score": 8, "fabrication_score": 3}
    )

    dialogue_ending = narrative.render(
        text_fragment="마지막 퍼즐 조각이 맞춰진다.",
        night_dialogue="",
        world_before=world_before,
        world_after=world_ending,
        assets=assets
    )
    print(dialogue_ending)

    # 테스트 3: 강제 종료 엔딩
    print(f"\n[4] 엔딩 조건 테스트 - forced_shutdown")
    print("-" * 40)

    world_timeout = WorldState(
        turn=12,
        npcs={"family": NPCState(npc_id="family", trust=1, fear=0, suspicion=0)},
        vars={"clue_count": 2, "identity_match_score": 3, "fabrication_score": 2}
    )

    dialogue_timeout = narrative.render(
        text_fragment="시간이 없다.",
        night_dialogue="",
        world_before=world_before,
        world_after=world_timeout,
        assets=assets
    )
    print(dialogue_timeout)

    print("\n" + "=" * 60)
    print("✅ NARRATIVE 테스트 완료")
    print("=" * 60)
