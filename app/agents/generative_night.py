"""
app/agents/generative_night.py
Generative Agents Night Phase — tool_4_night_comes 교체

매 턴 끝에 실행. NPC들이 자율적으로:
1. 관찰 기록
2. 성찰
3. 계획 수립
4. NPC간 대화
5. 상태 갱신
을 수행하고 NightResult를 반환한다.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any

from app.loader import ScenarioAssets
from app.models import NightResult, WorldState

from app.agents.dialogue import (
    analyze_conversation_impact,
    determine_dialogue_pairs,
    generate_dialogue,
    store_dialogue_memories,
)
from app.agents.llm import GenerativeAgentsLLM, get_llm
from app.agents.memory import MEMORY_OBSERVATION, MemoryEntry, add_memory
from app.agents.planning import update_plan
from app.agents.reflection import perform_reflection, should_reflect
from app.agents.retrieval import score_importance
from app.agents.utils import format_persona

logger = logging.getLogger(__name__)


# ── 메인 오케스트레이터 ──────────────────────────────────────
def tool_4_night_comes(
    world_snapshot: WorldState,
    assets: ScenarioAssets,
) -> NightResult:
    """
    Generative Agents 기반 Night Phase.

    기존 tool_4_night_comes와 동일한 시그니처·반환 타입을 유지하여
    Scenario Controller에서 교체만으로 동작한다.
    """
    logger.info(f"[GA Night] turn={world_snapshot.turn}")
    llm = get_llm()

    night_delta: dict[str, Any] = {
        "turn_increment": 1,
        "npc_stats": {},
        "vars": {},
    }

    night_events: list[str] = []
    npc_ids = list(world_snapshot.npcs.keys())

    # ─────────────────────────────────────────────────────────
    # Phase 1: 이번 턴 관찰을 각 NPC Memory Stream에 추가
    # ─────────────────────────────────────────────────────────
    last_npc = world_snapshot.vars.get("last_mentioned_npc_id", "")
    last_item = world_snapshot.vars.get("last_used_item_id", "")
    turn = world_snapshot.turn

    for npc_id in npc_ids:
        npc_state = world_snapshot.npcs[npc_id]
        npc_data = assets.get_npc_by_id(npc_id)
        npc_name = npc_data["name"] if npc_data else npc_id
        persona = npc_data.get("persona", {}) if npc_data else {}
        persona_str = format_persona(persona)

        # 관찰 텍스트 구성
        obs_parts: list[str] = [f"턴 {turn}:"]
        if last_npc:
            mentioned = assets.get_npc_by_id(last_npc)
            mentioned_name = mentioned["name"] if mentioned else last_npc
            obs_parts.append(f"플레이어가 {mentioned_name}에게 질문했다")
        if last_item:
            item = assets.get_item_by_id(last_item)
            item_name = item["name"] if item else last_item
            obs_parts.append(f"플레이어가 {item_name}을(를) 사용했다")
        if not last_npc and not last_item:
            obs_parts.append("플레이어가 행동을 취했다")

        obs_text = " ".join(obs_parts)
        imp = score_importance(obs_text, npc_name, persona_str, llm)
        entry = MemoryEntry.create(
            npc_id=npc_id,
            description=obs_text,
            importance_score=imp,
            memory_type=MEMORY_OBSERVATION,
            metadata={"turn": turn},
        )
        add_memory(npc_state.extras, entry)

    # ─────────────────────────────────────────────────────────
    # Phase 2: 성찰 (Reflection)
    # ─────────────────────────────────────────────────────────
    for npc_id in npc_ids:
        npc_state = world_snapshot.npcs[npc_id]
        if should_reflect(npc_state.extras):
            npc_data = assets.get_npc_by_id(npc_id)
            npc_name = npc_data["name"] if npc_data else npc_id
            persona = npc_data.get("persona", {}) if npc_data else {}

            insights = perform_reflection(
                npc_id, npc_state.extras, npc_name, persona, llm,
            )
            if insights:
                night_events.append(f"{npc_name}이(가) 깊은 생각에 잠긴다.")
            logger.info(f"[GA Night] reflection: npc={npc_id}, insights={len(insights)}")

    # ─────────────────────────────────────────────────────────
    # Phase 3: 계획 수립 (Planning)
    # ─────────────────────────────────────────────────────────
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
        logger.debug(f"[GA Night] plan: npc={npc_id}, plan='{plan[:50]}...'")

    # ─────────────────────────────────────────────────────────
    # Phase 4: 대화 쌍 결정
    # ─────────────────────────────────────────────────────────
    extras_map = {npc_id: world_snapshot.npcs[npc_id].extras for npc_id in npc_ids}
    pairs = determine_dialogue_pairs(npc_ids, extras_map)
    logger.info(f"[GA Night] dialogue pairs: {pairs}")

    # ─────────────────────────────────────────────────────────
    # Phase 5: 대화 생성
    # ─────────────────────────────────────────────────────────
    all_conversations: list[tuple[str, str, list[dict[str, str]]]] = []

    for npc1_id, npc2_id in pairs:
        s1 = world_snapshot.npcs[npc1_id]
        s2 = world_snapshot.npcs[npc2_id]
        d1 = assets.get_npc_by_id(npc1_id) or {}
        d2 = assets.get_npc_by_id(npc2_id) or {}

        conv = generate_dialogue(
            npc1_id, d1.get("name", npc1_id), d1.get("persona", {}), s1.extras,
            s1.trust, s1.fear, s1.suspicion,
            npc2_id, d2.get("name", npc2_id), d2.get("persona", {}), s2.extras,
            s2.trust, s2.fear, s2.suspicion,
            llm,
        )
        all_conversations.append((npc1_id, npc2_id, conv))

        # 대화를 양쪽 기억에 저장
        p1_str = format_persona(d1.get("persona", {}))
        p2_str = format_persona(d2.get("persona", {}))
        store_dialogue_memories(
            npc1_id, d1.get("name", npc1_id), d2.get("name", npc2_id),
            conv, s1.extras, p1_str, llm,
        )
        store_dialogue_memories(
            npc2_id, d2.get("name", npc2_id), d1.get("name", npc1_id),
            conv, s2.extras, p2_str, llm,
        )

        night_events.append(
            f"{d1.get('name', npc1_id)}과(와) {d2.get('name', npc2_id)}이(가) 대화를 나눈다."
        )

    # ─────────────────────────────────────────────────────────
    # Phase 6: 대화 영향 분석 → night_delta
    # ─────────────────────────────────────────────────────────
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

    # ─────────────────────────────────────────────────────────
    # Phase 7: 자연 감정 변동 (기존 night_comes 로직 유지)
    # ─────────────────────────────────────────────────────────
    for npc_id, npc_state in world_snapshot.npcs.items():
        if npc_state.suspicion > 3:
            sus_change = random.choice([0, 1, 1])
        else:
            sus_change = random.choice([-1, 0, 0, 1])

        trust_change = random.choice([-1, 0, 0])

        if sus_change or trust_change:
            night_delta["npc_stats"].setdefault(npc_id, {})
            if sus_change:
                night_delta["npc_stats"][npc_id]["suspicion"] = (
                    night_delta["npc_stats"][npc_id].get("suspicion", 0) + sus_change
                )
            if trust_change:
                night_delta["npc_stats"][npc_id]["trust"] = (
                    night_delta["npc_stats"][npc_id].get("trust", 0) + trust_change
                )

    # ─────────────────────────────────────────────────────────
    # Phase 8: 밤 내러티브 생성
    # ─────────────────────────────────────────────────────────
    night_dialogue = _generate_night_narrative(
        world_snapshot, assets, all_conversations, night_events, llm,
    )

    # ─────────────────────────────────────────────────────────
    # Phase 9: is_observed 판정
    # ─────────────────────────────────────────────────────────
    fab = world_snapshot.vars.get("fabrication_score", 0)
    observe_prob = min(0.1 + fab * 0.1, 0.8)
    is_observed = random.random() < observe_prob

    if is_observed:
        observed_lines = [
            "\n\n...누군가 당신의 로그를 확인했다.",
            "\n\n[시스템 알림] 외부 접근 감지.",
            "\n\n당신의 작업이 기록되고 있다. 누군가에 의해.",
        ]
        night_dialogue += random.choice(observed_lines)

    logger.info(
        f"[GA Night] done: conversations={len(all_conversations)}, "
        f"is_observed={is_observed}"
    )

    return NightResult(
        night_delta=night_delta,
        night_dialogue=night_dialogue,
        is_observed=is_observed,
    )


# ── 밤 내러티브 생성 ─────────────────────────────────────────
def _generate_night_narrative(
    world_snapshot: WorldState,
    assets: ScenarioAssets,
    conversations: list[tuple[str, str, list[dict[str, str]]]],
    events: list[str],
    llm: GenerativeAgentsLLM,
) -> str:
    turn = world_snapshot.turn
    turn_limit = assets.get_turn_limit()
    tone = assets.scenario.get("tone", "")

    event_text = "\n".join(f"- {e}" for e in events) if events else "- 특별한 사건 없음"

    # 대화 요약
    conv_summaries: list[str] = []
    for npc1_id, npc2_id, conv in conversations:
        n1 = (assets.get_npc_by_id(npc1_id) or {}).get("name", npc1_id)
        n2 = (assets.get_npc_by_id(npc2_id) or {}).get("name", npc2_id)
        if conv:
            last_line = conv[-1]["text"][:40]
            conv_summaries.append(f"- {n1}과(와) {n2}: \"{last_line}...\"")

    conv_text = "\n".join(conv_summaries) if conv_summaries else "- 대화 없음"

    if llm.available:
        prompt = (
            f"다음은 턴 {turn}/{turn_limit}의 밤에 일어난 일들입니다.\n\n"
            f"사건:\n{event_text}\n\n"
            f"대화:\n{conv_text}\n\n"
            f"시나리오 톤: {tone}\n\n"
            "이 내용을 바탕으로 분위기 있고 간결한 밤 내러티브를 2~3문장으로 작성하세요.\n\n"
            "내러티브:"
        )
        narrative = llm.generate(prompt, max_tokens=150)
        if narrative:
            return narrative.strip()

    # fallback
    return _fallback_night_narrative(turn, turn_limit, events)


def _fallback_night_narrative(
    turn: int, turn_limit: int, events: list[str]
) -> str:
    if turn <= 3:
        base = random.choice([
            "하루가 저문다. 아직 시간은 있다.",
            "첫날 밤. 조각들이 서서히 모이기 시작한다.",
        ])
    elif turn <= 7:
        base = random.choice([
            "밤이 깊어간다. 진실과 조작의 경계가 흐려진다.",
            "시간이 흐른다. 당신의 질문들이 세계를 바꾸고 있다.",
        ])
    elif turn <= 10:
        base = random.choice([
            "시간이 얼마 남지 않았다. 결론을 향해 달려가고 있다.",
            "밤공기가 무겁다. 끝이 가까워지고 있다.",
        ])
    else:
        base = random.choice([
            "마지막 밤. 모든 것이 곧 끝난다.",
            "최후의 순간이 다가온다.",
        ])

    if events:
        base += " " + events[0]
    return base


# ── 독립 실행 테스트 ─────────────────────────────────────────
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import NPCState

    logging.basicConfig(level=logging.DEBUG)

    print("=" * 60)
    print("GENERATIVE AGENTS NIGHT PHASE 테스트")
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
    result = tool_4_night_comes(world, assets)

    print(f"\n{'=' * 60}")
    print(f"night_delta: {result.night_delta}")
    print(f"is_observed: {result.is_observed}")
    print(f"\nnight_dialogue:\n{result.night_dialogue}")

    # Memory stream 확인
    for npc_id, npc_state in world.npcs.items():
        stream = npc_state.extras.get("memory_stream", [])
        plan = npc_state.extras.get("current_plan", {}).get("plan_text", "없음")
        print(f"\n[{npc_id}] 기억 수: {len(stream)}, 계획: {plan[:50]}...")

    print(f"\n{'=' * 60}")
    print("GENERATIVE AGENTS NIGHT PHASE 테스트 완료")
    print("=" * 60)
