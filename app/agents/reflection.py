"""
app/agents/reflection.py
Reflection 엔진 — Phase 전환 기반 성찰

NPC의 행동 단계(phase)가 전환될 때 성찰을 수행한다:
1. determine_current_phase(): stats 기반으로 현재 phase 판정
2. should_reflect(): phase 전환 여부 확인
3. perform_reflection(): 전환 시 질문/통찰 생성 → reflection 기억으로 저장
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
from app.agents.utils import format_persona

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 3
REFLECTION_WINDOW_TURNS = 5
MIN_IMPORTANCE_FOR_REFLECTION = 5.0


# ── Phase 판정 ────────────────────────────────────────────────
def determine_current_phase(
    npc_phases: list[dict[str, Any]],
    stats: dict[str, int],
) -> dict[str, Any]:
    """phases 순회, transition 조건 충족 시 다음 phase로 진행.

    Args:
        npc_phases: npcs.yaml에 정의된 phases 리스트
        stats: NPCState.stats (hits 카운터 포함)

    Returns:
        현재 적용되어야 할 phase dict
    """
    if not npc_phases:
        return {}

    current = npc_phases[0]
    for i, phase in enumerate(npc_phases[:-1]):
        cond = (phase.get("transition") or {}).get("condition", "")
        if cond and _evaluate_phase_condition(cond, stats):
            current = npc_phases[i + 1]
        else:
            break
    return current


def _evaluate_phase_condition(condition: str, stats: dict[str, int]) -> bool:
    """Phase 전환 조건 파싱 및 평가.

    지원 형식: 'minus_hits >= 3 OR critical_hits >= 1 OR affection <= 40'
    stats dict에서 key를 직접 조회 (hits도 stats에 포함).
    """
    if not condition:
        return False

    # OR로 분리
    or_clauses = [c.strip() for c in re.split(r'\bOR\b', condition, flags=re.IGNORECASE)]

    for clause in or_clauses:
        if _evaluate_single_condition(clause, stats):
            return True
    return False


def _evaluate_single_condition(clause: str, stats: dict[str, int]) -> bool:
    """단일 비교 조건 평가. 'key >= value' 또는 'key <= value' 형식."""
    # AND 지원
    and_parts = [p.strip() for p in re.split(r'\bAND\b', clause, flags=re.IGNORECASE)]
    if len(and_parts) > 1:
        return all(_evaluate_single_condition(p, stats) for p in and_parts)

    match = re.match(r'(\w+)\s*(>=|<=|>|<|==|!=)\s*(\d+)', clause.strip())
    if not match:
        return False

    key, op, val_str = match.group(1), match.group(2), match.group(3)
    current = stats.get(key, 0)
    target = int(val_str)

    if op == ">=":
        return current >= target
    elif op == "<=":
        return current <= target
    elif op == ">":
        return current > target
    elif op == "<":
        return current < target
    elif op == "==":
        return current == target
    elif op == "!=":
        return current != target
    return False


# ── 트리거 판정 ──────────────────────────────────────────────
def should_reflect(npc_memory: dict[str, Any], current_phase_id: str) -> bool:
    """Phase 전환 시 성찰 트리거.

    Args:
        npc_memory: NPCState.memory dict
        current_phase_id: 현재 판정된 phase의 ID
    """
    prev = npc_memory.get("last_reflected_phase_id")
    return prev != current_phase_id


# ── 후보 기억 수집 ───────────────────────────────────────────
def _get_reflection_candidates(
    npc_memory: dict[str, Any],
    current_turn: int,
    window_turns: int = REFLECTION_WINDOW_TURNS,
) -> list[MemoryEntry]:
    stream = get_memory_stream(npc_memory)
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
    current_phase: dict[str, Any],
    prev_phase_name: str,
    llm: GenerativeAgentsLLM,
    npc_id: str | None = None,
) -> list[str]:
    descs = "\n".join(f"- {m.description}" for m in memories)
    phase_name = current_phase.get("name", "새로운 단계")
    phase_goal = current_phase.get("goal", "")

    prompt = (
        f"{npc_name}은(는) 새로운 국면에 접어들었습니다.\n\n"
        f"[이전 단계] {prev_phase_name}\n"
        f"[새로운 단계] {phase_name}\n"
        f"목적: {phase_goal}\n\n"
        f"최근 기억:\n{descs}\n\n"
        f"이 전환을 바탕으로 {npc_name}이(가) 스스로에게 물을 수 있는 "
        f"통찰적인 질문 {MAX_QUESTIONS}가지를 생성하세요.\n\n"
        "질문 1:"
    )
    resp = llm.generate(prompt, max_tokens=200, npc_id=npc_id)
    if not resp:
        return [f"{npc_name}은(는) 새로운 국면에서 자신의 행동을 돌아본다."]

    questions = re.findall(r"질문\s*\d+\s*[:：]\s*(.+)", resp)
    if not questions:
        questions = [line.strip() for line in resp.strip().splitlines() if line.strip()]
    return questions[:MAX_QUESTIONS]


# ── 통찰 생성 ────────────────────────────────────────────────
def _generate_insights(
    questions: list[str],
    memories: list[MemoryEntry],
    npc_name: str,
    persona: dict[str, Any],
    current_phase: dict[str, Any],
    llm: GenerativeAgentsLLM,
    npc_id: str | None = None,
) -> list[str]:
    descs = "\n".join(f"- {m.description}" for m in memories)
    persona_str = format_persona(persona)
    phase_guide = current_phase.get("behavior_guide", "")
    insights: list[str] = []

    for q in questions:
        prompt = (
            f"NPC: {npc_name}\n"
            f"페르소나: {persona_str}\n"
            f"현재 단계 행동 가이드: {phase_guide}\n\n"
            f"최근 기억:\n{descs}\n\n"
            f"질문: {q}\n\n"
            "이 질문에 대한 통찰을 1~2문장으로 답변하세요:"
        )
        resp = llm.generate(prompt, max_tokens=100, npc_id=npc_id)
        insights.append(resp.strip() if resp else f"{npc_name}은(는) 아직 답을 찾지 못했다.")

    return insights


# ── 성찰 수행 (통합) ─────────────────────────────────────────
def perform_reflection(
    npc_id: str,
    npc_memory: dict[str, Any],
    npc_name: str,
    persona: dict[str, Any],
    llm: GenerativeAgentsLLM,
    current_turn: int,
    current_phase: dict[str, Any],
    prev_phase_id: str | None = None,
) -> list[str]:
    """Phase 전환 시 성찰 수행. 생성된 통찰 문자열 리스트 반환.

    Args:
        npc_memory: NPCState.memory dict
        current_phase: 새로 진입한 phase dict
        prev_phase_id: 이전 phase ID (없으면 초기 상태)
    """
    candidates = _get_reflection_candidates(npc_memory, current_turn)
    prev_phase_name = npc_memory.get("last_reflected_phase_name", "초기 상태")

    # LLM 사용 가능하면 전체 파이프라인, 아니면 간단 fallback
    if llm.available:
        if candidates:
            questions = _generate_questions(candidates, npc_name, current_phase, prev_phase_name, llm, npc_id=npc_id)
            insights = _generate_insights(questions, candidates, npc_name, persona, current_phase, llm, npc_id=npc_id)
        else:
            phase_name = current_phase.get("name", "새로운 단계")
            insights = [f"{npc_name}은(는) '{phase_name}' 단계로 접어들며 마음을 다잡는다."]
    else:
        phase_name = current_phase.get("name", "새로운 단계")
        insights = [f"{npc_name}은(는) '{phase_name}' 단계에 돌입하며 생각에 잠긴다."]

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
        add_memory(npc_memory, entry)

    # Phase 전환 기록
    npc_memory["last_reflected_phase_id"] = current_phase.get("phase_id")
    npc_memory["last_reflected_phase_name"] = current_phase.get("name", "")
    npc_memory["last_reflection_turn"] = current_turn

    logger.info(f"reflection: npc={npc_id} phase={current_phase.get('phase_id')} generated {len(insights)} insights")
    return insights
