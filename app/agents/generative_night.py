"""
app/agents/generative_night.py
NightController — Generative Agents (Park et al. 2023) 기반 밤 페이즈

낮 턴(5~10회) 이후 실행. NPC들이 자율적으로:
1. 성찰
2. 계획 수립
3. NPC간 대화 (랜덤 2명 × 2회)
4. 대화 영향 분석
을 수행하고 NightResult를 반환한다.

※ 밤 설명(night_description)은 GameLoop에서 NarrativeLayer를 통해 생성.
관찰 기록은 낮(ScenarioController)에서 이미 처리된 상태로 들어온다.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Optional

from app.loader import ScenarioAssets
from app.models import NightResult, WorldState

from app.agents.dialogue import (
    analyze_conversation_impact,
    generate_dialogue,
    store_dialogue_memories,
)
from app.llm import GenerativeAgentsLLM, get_llm
from app.agents.planning import update_plan
from app.agents.reflection import perform_reflection, should_reflect
from app.agents.utils import format_persona

logger = logging.getLogger(__name__)

NUM_DIALOGUE_ROUNDS = 2  # 대화 라운드 수 (매 라운드 랜덤 2명 선택)


class NightController:
    """
    밤 페이즈 컨트롤러 — ScenarioController와 병렬적으로 운용.

    ScenarioController가 낮 턴의 Tool 선택·실행 및 관찰 기록을 담당한다면,
    NightController는 밤 페이즈에서 NPC 자율 행동(성찰, 계획, 대화)을 오케스트레이션한다.
    """

    def __init__(self, llm: Optional[GenerativeAgentsLLM] = None):
        self._llm = llm

    @property
    def llm(self) -> GenerativeAgentsLLM:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    # ── 메인 실행 ─────────────────────────────────────────────
    def run(
        self,
        world_snapshot: WorldState,
        assets: ScenarioAssets,
    ) -> NightResult:
        """
        밤 페이즈 전체를 실행하고 NightResult를 반환한다.
        """
        logger.info(f"[NightController] turn={world_snapshot.turn}")
        llm = self.llm

        night_delta: dict[str, Any] = {
            "turn_increment": 1,
            "npc_stats": {},
            "vars": {},
        }

        night_events: list[str] = []
        npc_ids = list(world_snapshot.npcs.keys())
        turn = world_snapshot.turn

        # Phase 1: 성찰
        self._run_reflections(world_snapshot, assets, npc_ids, turn, llm, night_events)

        # Phase 2: 계획 수립
        self._run_planning(world_snapshot, assets, npc_ids, turn, llm)

        # Phase 3: 대화 생성 (랜덤 2명 × 2라운드)
        all_conversations = self._run_dialogues(world_snapshot, assets, npc_ids, turn, llm, night_events)

        # Phase 4: 대화 영향 분석
        self._analyze_impacts(all_conversations, assets, llm, night_delta)

        # night_conversation: 대화쌍별 중첩 리스트
        # (npc1_id, npc2_id도 함께 저장하여 NarrativeLayer에서 활용)
        night_conversation: list[list[dict[str, str]]] = [
            conv for _npc1_id, _npc2_id, conv in all_conversations
        ]

        # night_events도 저장 (NarrativeLayer에서 활용)
        # extras에 추가 정보 저장
        extras = {
            "night_events": night_events,
            "conversation_pairs": [
                (npc1_id, npc2_id) for npc1_id, npc2_id, _ in all_conversations
            ],
        }

        logger.info(
            f"[NightController] done: dialogue_rounds={len(all_conversations)}"
        )

        # ※ night_description은 빈 문자열로 반환
        # GameLoop에서 NarrativeLayer.render_night()를 호출하여 생성
        return NightResult(
            night_delta=night_delta,
            night_conversation=night_conversation,
            night_description="",  # GameLoop에서 NarrativeLayer로 생성
            extras=extras,
        )

    # ── Phase 1: 성찰 ────────────────────────────────────────
    def _run_reflections(
        self,
        world_snapshot: WorldState,
        assets: ScenarioAssets,
        npc_ids: list[str],
        turn: int,
        llm: GenerativeAgentsLLM,
        night_events: list[str],
    ) -> None:
        for npc_id in npc_ids:
            npc_state = world_snapshot.npcs[npc_id]
            if should_reflect(npc_state.extras):
                npc_data = assets.get_npc_by_id(npc_id)
                npc_name = npc_data["name"] if npc_data else npc_id
                persona = npc_data.get("persona", {}) if npc_data else {}

                insights = perform_reflection(
                    npc_id, npc_state.extras, npc_name, persona, llm, current_turn=turn,
                )
                if insights:
                    night_events.append(f"{npc_name}이(가) 깊은 생각에 잠긴다.")
                logger.info(f"[NightController] reflection: npc={npc_id}, insights={len(insights)}")

    # ── Phase 2: 계획 수립 ────────────────────────────────────
    def _run_planning(
        self,
        world_snapshot: WorldState,
        assets: ScenarioAssets,
        npc_ids: list[str],
        turn: int,
        llm: GenerativeAgentsLLM,
    ) -> None:
        scenario_title = assets.scenario.get("title", "")
        turn_limit = assets.get_turn_limit()

        for npc_id in npc_ids:
            npc_state = world_snapshot.npcs[npc_id]
            npc_data = assets.get_npc_by_id(npc_id)
            npc_name = npc_data["name"] if npc_data else npc_id
            persona = npc_data.get("persona", {}) if npc_data else {}

            plan = update_plan(
                npc_id, npc_name, persona, npc_state.extras,
                npc_state.trust, npc_state.fear, npc_state.suspicion,
                turn, turn_limit, scenario_title, llm,
            )
            logger.debug(f"[NightController] plan: npc={npc_id}, plan='{plan[:50]}...'")

    # ── Phase 3: 대화 생성 (랜덤 2명 × NUM_DIALOGUE_ROUNDS) ──
    def _run_dialogues(
        self,
        world_snapshot: WorldState,
        assets: ScenarioAssets,
        npc_ids: list[str],
        turn: int,
        llm: GenerativeAgentsLLM,
        night_events: list[str],
    ) -> list[tuple[str, str, list[dict[str, str]]]]:
        if len(npc_ids) < 2:
            return []

        all_conversations: list[tuple[str, str, list[dict[str, str]]]] = []

        for _ in range(NUM_DIALOGUE_ROUNDS):
            pair = random.sample(npc_ids, 2)
            npc1_id, npc2_id = pair[0], pair[1]

            s1 = world_snapshot.npcs[npc1_id]
            s2 = world_snapshot.npcs[npc2_id]
            d1 = assets.get_npc_by_id(npc1_id) or {}
            d2 = assets.get_npc_by_id(npc2_id) or {}

            conv = generate_dialogue(
                npc1_id, d1.get("name", npc1_id), d1.get("persona", {}), s1.extras,
                s1.trust, s1.fear, s1.suspicion,
                npc2_id, d2.get("name", npc2_id), d2.get("persona", {}), s2.extras,
                s2.trust, s2.fear, s2.suspicion,
                llm, current_turn=turn,
            )
            all_conversations.append((npc1_id, npc2_id, conv))

            p1_str = format_persona(d1.get("persona", {}))
            p2_str = format_persona(d2.get("persona", {}))
            store_dialogue_memories(
                npc1_id, d1.get("name", npc1_id), d2.get("name", npc2_id),
                conv, s1.extras, p1_str, llm, current_turn=turn,
            )
            store_dialogue_memories(
                npc2_id, d2.get("name", npc2_id), d1.get("name", npc1_id),
                conv, s2.extras, p2_str, llm, current_turn=turn,
            )

            night_events.append(
                f"{d1.get('name', npc1_id)}과(와) {d2.get('name', npc2_id)}이(가) 대화를 나눈다."
            )

        logger.info(f"[NightController] dialogue rounds: {len(all_conversations)}")
        return all_conversations

    # ── Phase 4: 대화 영향 분석 ───────────────────────────────
    def _analyze_impacts(
        self,
        all_conversations: list[tuple[str, str, list[dict[str, str]]]],
        assets: ScenarioAssets,
        llm: GenerativeAgentsLLM,
        night_delta: dict[str, Any],
    ) -> None:
        for npc1_id, npc2_id, conv in all_conversations:
            d1 = assets.get_npc_by_id(npc1_id) or {}
            d2 = assets.get_npc_by_id(npc2_id) or {}
            changes = analyze_conversation_impact(
                npc1_id, d1.get("name", npc1_id), d1.get("persona", {}),
                npc2_id, d2.get("name", npc2_id), d2.get("persona", {}),
                conv, llm,
            )
            for npc_id, stat_changes in changes.items():
                if not stat_changes:
                    continue
                night_delta["npc_stats"].setdefault(npc_id, {})
                for stat, val in stat_changes.items():
                    night_delta["npc_stats"][npc_id][stat] = (
                        night_delta["npc_stats"][npc_id].get(stat, 0) + val
                    )

# ── 싱글턴 ────────────────────────────────────────────────────
_night_controller_instance: Optional[NightController] = None


def get_night_controller() -> NightController:
    """NightController 싱글턴 인스턴스 반환"""
    global _night_controller_instance
    if _night_controller_instance is None:
        _night_controller_instance = NightController()
    return _night_controller_instance


# ── 독립 실행 테스트 ─────────────────────────────────────────
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import NPCState

    logging.basicConfig(level=logging.DEBUG)

    print("=" * 60)
    print("NIGHT CONTROLLER 테스트")
    print("=" * 60)

    base_path = Path(__file__).parent.parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()
    if not scenarios:
        print("시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n시나리오: {assets.scenario.get('title')}")

    world = WorldState(
        turn=3,
        npcs={
            "family": NPCState(npc_id="family", trust=2, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=1, fear=0, suspicion=2),
            "witness": NPCState(npc_id="witness", trust=0, fear=3, suspicion=1),
        },
        inventory=["casefile_brief", "pattern_analyzer", "memo_pad"],
        vars={
            "clue_count": 2,
            "identity_match_score": 1,
            "fabrication_score": 1,
            "last_mentioned_npc_id": "family",
        },
    )

    print("\n실행 중...")
    controller = NightController()
    result = controller.run(world, assets)

    print(f"\n{'=' * 60}")
    print(f"night_delta: {result.night_delta}")
    print(f"\nnight_description:\n{result.night_description}")
    print(f"\nnight_conversation ({len(result.night_conversation)} rounds):")
    for i, conv in enumerate(result.night_conversation):
        print(f"\n  [Round {i+1}] ({len(conv)} utterances)")
        for utt in conv:
            print(f"    {utt['speaker']}: {utt['text']}")

    for npc_id, npc_state in world.npcs.items():
        stream = npc_state.extras.get("memory_stream", [])
        plan = npc_state.extras.get("current_plan", {}).get("plan_text", "없음")
        print(f"\n[{npc_id}] 기억 수: {len(stream)}, 계획: {plan[:50]}...")

    print(f"\n{'=' * 60}")
    print("NIGHT CONTROLLER 테스트 완료")
    print("=" * 60)
