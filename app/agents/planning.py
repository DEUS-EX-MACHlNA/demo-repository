"""
app/agents/planning.py
Planning 시스템 — Phase 기반 가족 회의

- Long-term Plan: 게임 시작 시 1회 생성 (game.py에서 호출)
- Short-term Plan: 매 밤 파이프라인에서 생성 (night_controller에서 호출)
- format_agenda_items: 낮 행동 로그를 가족 회의 안건으로 포맷팅
"""
from __future__ import annotations

import logging
from typing import Any

from app.llm import GenerativeAgentsLLM
from app.agents.memory import MEMORY_PLAN, MemoryEntry, add_memory
from app.agents.retrieval import retrieve_memories, score_importance
from app.agents.utils import format_emotion, format_persona

logger = logging.getLogger(__name__)


def generate_long_term_plan(
    npc_id: str,
    npc_name: str,
    persona: dict[str, Any],
    npc_goal: str,
    initial_phase: dict[str, Any],
    stats: dict[str, int],
    scenario_title: str,
    llm: GenerativeAgentsLLM,
) -> str:
    """게임 시작 시 1회 호출. YAML의 goal + 초기 phase를 기반으로 장기 전략 생성.

    Args:
        npc_goal: npcs.yaml의 goal 필드
        initial_phase: phases[0] dict (name, goal, behavior_guide)
        stats: NPCState.stats
    """
    persona_str = format_persona(persona)
    emotion_str = format_emotion(stats)

    prompt = (
        f"당신은 '{scenario_title}' 시나리오 속 {npc_name}입니다.\n\n"
        f"[최상위 목표]\n{npc_goal}\n\n"
        f"[초기 단계: {initial_phase.get('name', '초기')}]\n"
        f"목적: {initial_phase.get('goal', '')}\n"
        f"행동 가이드: {initial_phase.get('behavior_guide', '')}\n\n"
        f"[페르소나]\n{persona_str}\n\n"
        f"[현재 감정 상태]\n{emotion_str}\n\n"
        "위 최상위 목표를 달성하기 위한 전체적인 전략을 2~3문장으로 서술하세요.\n\n"
        "전략:"
    )
    plan = llm.generate(prompt, max_tokens=150)
    if not plan:
        plan = f"{npc_name}은(는) 상황을 주시하며 기회를 엿본다."
    logger.info(f"long_term_plan: npc={npc_id} plan='{plan[:60]}...'")
    return plan.strip()


def generate_short_term_plan(
    npc_id: str,
    npc_name: str,
    persona: dict[str, Any],
    npc_memory: dict[str, Any],
    stats: dict[str, int],
    long_term_plan: str,
    current_phase: dict[str, Any],
    day_action_log: list[dict[str, Any]],
    llm: GenerativeAgentsLLM,
    current_turn: int = 1,
) -> str:
    """매 밤 호출. 가족 회의 안건 기반 단기 계획 생성.

    Args:
        npc_memory: NPCState.memory dict
        stats: NPC 스탯 Dict
        long_term_plan: 장기 전략 텍스트
        current_phase: 현재 phase dict
        day_action_log: 낮 행동 로그 리스트
    """
    persona_str = format_persona(persona)
    emotion_str = format_emotion(stats)

    # 안건 포맷팅
    agenda = format_agenda_items(day_action_log, persona)

    # 최근 기억 검색
    query = f"{npc_name}의 다음 행동 계획"
    recent = retrieve_memories(npc_memory, query, llm, current_turn=current_turn, k=3)
    memory_ctx = "\n".join(f"- {m.description}" for m in recent) if recent else "(최근 기억 없음)"

    phase_name = current_phase.get("name", "현재 단계")
    behavior_guide = current_phase.get("behavior_guide", "")

    prompt = (
        f"당신은 {npc_name}입니다. 지금은 밤, 가족 회의 시간입니다.\n\n"
        f"[현재 단계: {phase_name}]\n"
        f"행동 가이드: {behavior_guide}\n\n"
        f"[페르소나]\n{persona_str}\n\n"
        f"[현재 감정 상태]\n{emotion_str}\n\n"
        f"[장기 전략]\n{long_term_plan}\n\n"
        f"[오늘 낮 플레이어의 행동 — 가족 회의 안건]\n{agenda}\n\n"
        f"[최근 기억]\n{memory_ctx}\n\n"
        "위 안건들을 검토한 뒤 1~2문장으로 답하세요:\n"
        "1. 가장 우려되는/주목할 안건은?\n"
        "2. 내일 낮에 플레이어를 어떻게 대할 것인가?\n\n"
        "계획:"
    )
    plan = llm.generate(prompt, max_tokens=120)
    if not plan:
        plan = f"{npc_name}은(는) 내일도 같은 태도로 플레이어를 지켜볼 것이다."
    logger.debug(f"short_term_plan: npc={npc_id} plan='{plan[:60]}...'")

    # 계획을 기억으로 저장
    persona_str_for_score = format_persona(persona)
    imp = score_importance(plan, npc_name, persona_str_for_score, llm)
    entry = MemoryEntry.create(
        npc_id=npc_id,
        description=f"[계획] {plan.strip()}",
        importance_score=imp,
        current_turn=current_turn,
        memory_type=MEMORY_PLAN,
    )
    add_memory(npc_memory, entry)

    return plan.strip()


def format_agenda_items(
    day_action_log: list[dict[str, Any]],
    persona: dict[str, Any],
) -> str:
    """낮 행동 로그를 가족 회의 안건 형식으로 포맷팅.

    trigger 매칭으로 [치명적]/[위험] 태그를 부착.
    hits 갱신은 낮 파이프라인(dialogue.py)에서 별도 처리.

    Args:
        day_action_log: [{turn, input, intent, events}, ...]
        persona: NPC의 persona dict (triggers 포함)
    """
    if not day_action_log:
        return "(오늘 특별한 안건 없음)"

    triggers = persona.get("triggers", {})
    critical_triggers = triggers.get("critical", [])
    minus_triggers = triggers.get("minus", [])

    lines: list[str] = []
    for entry in day_action_log:
        turn = entry.get("turn", "?")
        user_input = entry.get("input", "")
        intent = entry.get("intent", "neutral")
        events = entry.get("events", [])

        # 안건 텍스트 조합
        event_text = "; ".join(events) if events else user_input

        # trigger 태그 부착
        tag = ""
        for ct in critical_triggers:
            if ct in user_input or ct in event_text:
                tag = "[치명적] "
                break
        if not tag:
            for mt in minus_triggers:
                if mt in user_input or mt in event_text:
                    tag = "[위험] "
                    break

        lines.append(f"- {tag}턴{turn}: {event_text} (의도: {intent})")

    return "\n".join(lines)
