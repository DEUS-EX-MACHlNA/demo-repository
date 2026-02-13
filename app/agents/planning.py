"""
app/agents/planning.py
Planning 시스템 — Generative Agents (Park et al. 2023) Section 3.4

장기 계획(시나리오 수준)과 단기 계획(턴 수준)을 생성한다.
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
    turn: int,
    turn_limit: int,
    scenario_title: str,
    llm: GenerativeAgentsLLM,
) -> str:
    """시나리오 수준 장기 계획 (최초 1회 또는 주요 사건 후 재생성)."""
    persona_str = format_persona(persona)
    prompt = (
        f"당신은 '{scenario_title}' 시나리오 속 {npc_name}입니다.\n\n"
        f"페르소나:\n{persona_str}\n\n"
        f"현재 턴: {turn}/{turn_limit}\n\n"
        f"이 시나리오가 끝날 때까지의 전체적인 목표와 계획을 2~3문장으로 서술하세요.\n\n"
        "계획:"
    )
    plan = llm.generate(prompt=prompt, max_tokens=150)
    if not plan:
        plan = f"{npc_name}은(는) 상황을 주시하며 기회를 엿본다."
    logger.debug(f"long_term_plan: npc={npc_id} plan='{plan[:60]}...'")
    return plan.strip()


def generate_short_term_plan(
    npc_id: str,
    npc_name: str,
    persona: dict[str, Any],
    npc_memory: dict[str, Any],
    stats: dict[str, int],
    long_term_plan: str,
    llm: GenerativeAgentsLLM,
    current_turn: int = 1,
) -> str:
    """턴 수준 단기 계획.

    Args:
        npc_memory: NPCState.memory dict
        stats: NPC 스탯 Dict (예: {"affection": 50, "fear": 80})
    """
    persona_str = format_persona(persona)
    emotion_str = format_emotion(stats)

    # 최근 기억 검색
    query = f"{npc_name}의 다음 행동 계획"
    recent = retrieve_memories(npc_memory, query, llm, current_turn=current_turn, k=5)
    memory_ctx = "\n".join(f"- {m.description}" for m in recent) if recent else "(최근 기억 없음)"

    prompt = (
        f"당신은 {npc_name}입니다.\n\n"
        f"페르소나: {persona_str}\n"
        f"현재 감정: {emotion_str}\n"
        f"장기 계획: {long_term_plan}\n\n"
        f"최근 일어난 일:\n{memory_ctx}\n\n"
        "다음 턴에 무엇을 할 계획인지 1~2문장으로 답하세요.\n\n"
        "계획:"
    )
    plan = llm.generate(prompt=prompt, max_tokens=80)
    if not plan:
        plan = f"{npc_name}은(는) 다른 사람들과 대화를 나누어 보려 한다."
    logger.debug(f"short_term_plan: npc={npc_id} plan='{plan[:60]}...'")
    return plan.strip()


def update_plan(
    npc_id: str,
    npc_name: str,
    persona: dict[str, Any],
    npc_memory: dict[str, Any],
    stats: dict[str, int],
    turn: int,
    turn_limit: int,
    scenario_title: str,
    llm: GenerativeAgentsLLM,
) -> str:
    """장기+단기 계획을 갱신하고 memory에 저장. 단기 계획 텍스트 반환.

    Args:
        npc_memory: NPCState.memory dict
        stats: NPC 스탯 Dict (예: {"affection": 50, "fear": 80})
    """
    # 장기 계획 (없으면 생성)
    if "long_term_plan" not in npc_memory:
        lt_plan = generate_long_term_plan(
            npc_id, npc_name, persona, turn, turn_limit, scenario_title, llm,
        )
        npc_memory["long_term_plan"] = lt_plan
    else:
        lt_plan = npc_memory["long_term_plan"]

    # 단기 계획
    st_plan = generate_short_term_plan(
        npc_id, npc_name, persona, npc_memory,
        stats, lt_plan, llm, current_turn=turn,
    )

    # memory에 저장
    npc_memory["current_plan"] = {
        "plan_text": st_plan,
        "created_at_turn": turn,
    }

    # 계획을 기억으로 저장
    persona_str = format_persona(persona)
    imp = score_importance(st_plan, npc_name, persona_str, llm)
    entry = MemoryEntry.create(
        npc_id=npc_id,
        description=f"[계획] {st_plan}",
        importance_score=imp,
        current_turn=turn,
        memory_type=MEMORY_PLAN,
    )
    add_memory(npc_memory, entry)

    return st_plan
