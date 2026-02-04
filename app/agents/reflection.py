"""
app/agents/reflection.py
Reflection 엔진 — Generative Agents (Park et al. 2023) Section 3.3

누적 중요도가 threshold를 넘으면:
1. 최근 고중요도 기억 수집
2. 성찰 질문 생성 (LLM)
3. 질문에 답변 → 통찰 생성 (LLM)
4. 통찰을 reflection 기억으로 저장
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.llm import GenerativeAgentsLLM
from app.agents.memory import (
    MEMORY_REFLECTION,
    MemoryEntry,
    add_memory,
    get_memory_stream,
)
from app.agents.retrieval import score_importance
from app.agents.utils import extract_number, format_persona

logger = logging.getLogger(__name__)

REFLECTION_THRESHOLD = 40.0
REFLECTION_WINDOW_TURNS = 5
MIN_IMPORTANCE_FOR_REFLECTION = 5.0
MAX_QUESTIONS = 3


# ── 트리거 판정 ──────────────────────────────────────────────
def should_reflect(npc_extras: dict[str, Any]) -> bool:
    acc = npc_extras.get("accumulated_importance", 0.0)
    threshold = npc_extras.get("reflection_threshold", REFLECTION_THRESHOLD)
    return acc >= threshold


# ── 후보 기억 수집 ───────────────────────────────────────────
def _get_reflection_candidates(
    npc_extras: dict[str, Any],
    current_turn: int,
    window_turns: int = REFLECTION_WINDOW_TURNS,
) -> list[MemoryEntry]:
    stream = get_memory_stream(npc_extras)
    cutoff = current_turn - window_turns
    candidates = [
        m for m in stream
        if m.creation_turn >= cutoff and m.importance_score >= MIN_IMPORTANCE_FOR_REFLECTION
    ]
    candidates.sort(key=lambda m: m.importance_score, reverse=True)
    return candidates[:10]


# ── 성찰 질문 생성 ───────────────────────────────────────────
def _generate_questions(
    memories: list[MemoryEntry],
    npc_name: str,
    llm: GenerativeAgentsLLM,
) -> list[str]:
    descs = "\n".join(f"- {m.description}" for m in memories)
    prompt = (
        f"다음은 {npc_name}의 최근 기억들입니다:\n\n"
        f"{descs}\n\n"
        f"이 기억들을 바탕으로 {npc_name}이(가) 스스로에게 물을 수 있는 "
        f"통찰적인 질문 {MAX_QUESTIONS}가지를 생성하세요.\n\n"
        "질문 1:"
    )
    resp = llm.generate(prompt, max_tokens=200)
    if not resp:
        return [f"{npc_name}은(는) 최근 일어난 일들을 되짚어본다."]

    questions = re.findall(r"질문\s*\d+\s*[:：]\s*(.+)", resp)
    if not questions:
        # 줄 단위로 fallback
        questions = [line.strip() for line in resp.strip().splitlines() if line.strip()]
    return questions[:MAX_QUESTIONS]


# ── 통찰 생성 ────────────────────────────────────────────────
def _generate_insights(
    questions: list[str],
    memories: list[MemoryEntry],
    npc_name: str,
    persona: dict[str, Any],
    llm: GenerativeAgentsLLM,
) -> list[str]:
    descs = "\n".join(f"- {m.description}" for m in memories)
    persona_str = format_persona(persona)
    insights: list[str] = []

    for q in questions:
        prompt = (
            f"NPC: {npc_name}\n"
            f"페르소나: {persona_str}\n\n"
            f"최근 기억:\n{descs}\n\n"
            f"질문: {q}\n\n"
            "이 질문에 대한 통찰을 1~2문장으로 답변하세요:"
        )
        resp = llm.generate(prompt, max_tokens=100)
        insights.append(resp.strip() if resp else f"{npc_name}은(는) 아직 답을 찾지 못했다.")

    return insights


# ── 성찰 수행 (통합) ─────────────────────────────────────────
def perform_reflection(
    npc_id: str,
    npc_extras: dict[str, Any],
    npc_name: str,
    persona: dict[str, Any],
    llm: GenerativeAgentsLLM,
    current_turn: int,
) -> list[str]:
    """성찰 전 과정 수행. 생성된 통찰 문자열 리스트 반환."""
    candidates = _get_reflection_candidates(npc_extras, current_turn)
    if not candidates:
        logger.debug(f"reflection: npc={npc_id} — no candidates")
        return []

    # LLM 사용 가능하면 전체 파이프라인, 아니면 간단 fallback
    if llm.available:
        questions = _generate_questions(candidates, npc_name, llm)
        insights = _generate_insights(questions, candidates, npc_name, persona, llm)
    else:
        insights = [f"{npc_name}은(는) 최근 일을 곱씹으며 생각에 잠긴다."]

    # 통찰을 reflection 기억으로 저장
    persona_str = format_persona(persona)
    for insight in insights:
        imp = score_importance(insight, npc_name, persona_str, llm)
        imp = max(imp, 7.0)  # 성찰은 최소 중요도 7
        entry = MemoryEntry.create(
            npc_id=npc_id,
            description=insight,
            importance_score=imp,
            current_turn=current_turn,
            memory_type=MEMORY_REFLECTION,
        )
        add_memory(npc_extras, entry)

    # 누적 중요도 리셋
    npc_extras["accumulated_importance"] = 0.0
    npc_extras["last_reflection_turn"] = current_turn

    logger.info(f"reflection: npc={npc_id} generated {len(insights)} insights")
    return insights
