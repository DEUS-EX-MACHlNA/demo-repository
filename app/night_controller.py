"""
app/night_controller.py
Night Phase Controller — Generative Agents (Park et al. 2023) 기반

낮 턴 이후 실행. NPC들이 자율적으로:
1. 성찰 (Reflection)
2. 계획 수립 (Planning)
3. 그룹 대화 (Group Dialogue) — NPC 3명이 함께 대화
4. 대화 영향 분석 (Impact Analysis)
을 수행하고 NightResult를 반환한다.

NPCState가 stats Dict 기반으로 변경됨.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Optional

from app.loader import ScenarioAssets
from app.schemas import NightResult, WorldState

from app.agents.dialogue import (
    generate_utterance,
    analyze_conversation_impact,
    store_dialogue_memories,
)
from app.llm import GenerativeAgentsLLM, get_llm
from app.agents.planning import update_plan
from app.agents.reflection import perform_reflection, should_reflect
from app.agents.utils import format_persona

logger = logging.getLogger(__name__)

NUM_GROUP_UTTERANCES = 6  # 그룹 대화 발화 횟수


class NightController:
    """
    밤 페이즈 컨트롤러 — DayController와 병렬적으로 운용.

    DayController가 낮 턴의 Tool 선택·실행 및 관찰 기록을 담당한다면,
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
    def process(
        self,
        world_snapshot: WorldState,
        assets: ScenarioAssets,
    ) -> NightResult:
        """
        밤 페이즈를 처리하고 NightResult를 반환한다.
        """
        logger.info(f"[NightController] 처리 시작: turn={world_snapshot.turn}")
        llm = self.llm

        night_delta: dict[str, Any] = {
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

        # Phase 3: 그룹 대화 생성 (3명이 함께 대화)
        night_conversation = self._run_dialogues(world_snapshot, assets, npc_ids, turn, llm)

        # Phase 4: 대화 영향 분석
        night_description = self._analyze_impacts(night_conversation, npc_ids, assets, llm, night_delta)

        logger.info(
            f"[NightController] done: utterances={len(night_conversation)}, descriptions={len(night_description)}"
        )

        return NightResult(
            night_delta=night_delta,
            night_conversation=night_conversation,
            night_description=night_description,
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
            # memory Dict 사용 (이전의 extras)
            if should_reflect(npc_state.memory):
                npc_data = assets.get_npc_by_id(npc_id)
                npc_name = npc_data["name"] if npc_data else npc_id
                persona = npc_data.get("persona", {}) if npc_data else {}

                insights = perform_reflection(
                    npc_id, npc_state.memory, npc_name, persona, llm, current_turn=turn,
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
                npc_id, npc_name, persona, npc_state.memory,
                npc_state.stats,
                turn, turn_limit, scenario_title, llm,
            )
            logger.debug(f"[NightController] plan: npc={npc_id}, plan='{plan[:50]}...'")

    # ── Phase 3: 그룹 대화 생성 (3명이 함께, 랜덤 발화자 선택) ──
    def _run_dialogues(
        self,
        world_snapshot: WorldState,
        assets: ScenarioAssets,
        npc_ids: list[str],
        turn: int,
        llm: GenerativeAgentsLLM,
    ) -> list[dict[str, str]]:
        """Caroline의 NPC 3명이 함께 대화. 총 6번 발화."""
        if len(npc_ids) < 2:
            return []

        conversation: list[dict[str, str]] = []

        # NPC 정보 준비
        npc_info: dict[str, dict[str, Any]] = {}
        for npc_id in npc_ids:
            state = world_snapshot.npcs[npc_id]
            data = assets.get_npc_by_id(npc_id) or {}
            npc_info[npc_id] = {
                "state": state,
                "data": data,
                "name": data.get("name", npc_id),
                "persona": data.get("persona", {}),
            }

        # 6번 발화 (랜덤 발화자 선택)
        for _ in range(NUM_GROUP_UTTERANCES):
            speaker_id = random.choice(npc_ids)
            speaker = npc_info[speaker_id]
            state = speaker["state"]

            # listener는 다른 모든 NPC의 이름
            other_names = [
                info["name"] for nid, info in npc_info.items() if nid != speaker_id
            ]
            listener_str = ", ".join(other_names)

            utterance = generate_utterance(
                speaker_id,
                speaker["name"],
                speaker["persona"],
                state.memory,
                state.stats,
                listener_str,
                conversation,
                llm,
                current_turn=turn,
            )
            conversation.append({"speaker": speaker["name"], "text": utterance})

        # 대화 내용을 모든 NPC의 기억에 저장
        for npc_id in npc_ids:
            info = npc_info[npc_id]
            other_names = [
                n_info["name"] for nid, n_info in npc_info.items() if nid != npc_id
            ]
            store_dialogue_memories(
                npc_id,
                info["name"],
                ", ".join(other_names),
                conversation,
                info["state"].memory,
                format_persona(info["persona"]),
                llm,
                current_turn=turn,
            )

        logger.info(f"[NightController] group dialogue: {len(conversation)} utterances")
        return conversation

    # ── Phase 4: 대화 영향 분석 ───────────────────────────────
    def _analyze_impacts(
        self,
        conversation: list[dict[str, str]],
        npc_ids: list[str],
        assets: ScenarioAssets,
        llm: GenerativeAgentsLLM,
        night_delta: dict[str, Any],
    ) -> list[str]:
        """그룹 대화가 각 NPC에 미친 영향 분석.

        모든 NPC 쌍에 대해 analyze_conversation_impact를 호출하여 집계.

        Returns:
            night_description: 대화에서 발생한 핵심 사건 묘사 리스트
        """
        night_description: list[str] = []

        if len(npc_ids) < 2:
            return night_description

        stat_names = assets.get_npc_stat_names()

        # 모든 NPC 쌍에 대해 분석
        for i, npc1_id in enumerate(npc_ids):
            for npc2_id in npc_ids[i + 1:]:
                d1 = assets.get_npc_by_id(npc1_id) or {}
                d2 = assets.get_npc_by_id(npc2_id) or {}
                result = analyze_conversation_impact(
                    npc1_id, d1.get("name", npc1_id), d1.get("persona", {}),
                    npc2_id, d2.get("name", npc2_id), d2.get("persona", {}),
                    conversation, llm,
                    stat_names=stat_names,
                )

                # npc_stats 집계
                npc_stats = result.get("npc_stats", {})
                for npc_id, stat_changes in npc_stats.items():
                    if not stat_changes:
                        continue
                    night_delta["npc_stats"].setdefault(npc_id, {})
                    for stat, val in stat_changes.items():
                        night_delta["npc_stats"][npc_id][stat] = (
                            night_delta["npc_stats"][npc_id].get(stat, 0) + val
                        )

                # event_description 수집
                night_description.extend(result.get("event_description", []))

        return night_description


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
    from app.schemas import NPCState

    logging.basicConfig(level=logging.DEBUG)

    print("=" * 60)
    print("NIGHT CONTROLLER 테스트")
    print("=" * 60)

    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()
    if not scenarios:
        print("시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n시나리오: {assets.scenario.get('title')}")

    # NPCState를 시나리오 YAML의 stats 구조에 맞춤
    world = WorldState(
        turn=3,
        npcs={
            "stepmother": NPCState(
                npc_id="stepmother",
                stats={"affection": 50, "fear": 80, "humanity": 0}
            ),
            "stepfather": NPCState(
                npc_id="stepfather",
                stats={"affection": 30, "fear": 60, "humanity": 20}
            ),
            "brother": NPCState(
                npc_id="brother",
                stats={"affection": 60, "fear": 40, "humanity": 50}
            ),
        },
        inventory=[],
        vars={
            "humanity": 100,
            "suspicion_level": 0,
        },
    )

    print("\n실행 중...")
    controller = NightController()
    result = controller.process(world, assets)

    print(f"\n{'=' * 60}")
    print(f"night_delta: {result.night_delta}")
    print(f"\nnight_conversation ({len(result.night_conversation)} utterances):")
    for utt in result.night_conversation:
        print(f"  {utt['speaker']}: {utt['text']}")

    for npc_id, npc_state in world.npcs.items():
        stream = npc_state.memory.get("memory_stream", [])
        plan = npc_state.memory.get("current_plan", {}).get("plan_text", "없음")
        print(f"\n[{npc_id}] 기억 수: {len(stream)}, 계획: {plan[:50]}...")

    print(f"\n{'=' * 60}")
    print("NIGHT CONTROLLER 테스트 완료")
    print("=" * 60)
