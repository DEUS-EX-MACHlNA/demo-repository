"""
app/agents/retrieval.py
Memory Retrieval — α·recency + β·importance + γ·relevance

Park et al. 2023, Section 3.2
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

from app.llm import GenerativeAgentsLLM
from app.agents.memory import MemoryEntry, get_memory_stream
from app.agents.utils import extract_number

logger = logging.getLogger(__name__)

# ── 기본 하이퍼파라미터 ──────────────────────────────────────
ALPHA = 1.0  # recency 가중치
BETA = 1.0   # importance 가중치
GAMMA = 1.0  # relevance 가중치
DECAY_FACTOR = 0.95  # 턴당 감쇄
DEFAULT_K = 5


# ── Recency ──────────────────────────────────────────────────
def _recency_score(memory: MemoryEntry, current_turn: int) -> float:
    turns_elapsed = max(current_turn - memory.last_access_turn, 0)
    return DECAY_FACTOR ** turns_elapsed


# ── Importance (이미 MemoryEntry에 저장된 값 사용) ────────────
def _importance_score(memory: MemoryEntry) -> float:
    return memory.importance_score / 10.0


# ── Relevance ────────────────────────────────────────────────
def _relevance_score_llm(memory_text: str, query: str, llm: GenerativeAgentsLLM) -> float:
    """LLM 기반 관련성 채점 (1‑10 → 0‑1)."""
    # if not llm.available:
    #     return _relevance_score_keyword(memory_text, query)

    # prompt = (
    #     "다음 두 내용의 관련성을 1~10 정수로만 답하세요.\n\n"
    #     f'기억: "{memory_text}"\n'
    #     f'상황: "{query}"\n\n'
    #     "관련성 점수:"
    # )
    # resp = llm.generate(prompt, max_tokens=5, temperature=0.1)
    # score = extract_number(resp, default=5.0)
    # return min(max(score, 1.0), 10.0) / 10.0

    # Token-Based Relevance only for now
    return _relevance_score_keyword(memory_text, query)


def _relevance_score_keyword(memory_text: str, query: str) -> float:
    """키워드 겹침 기반 간단한 관련성 (fallback)."""
    mem_tokens = set(re.findall(r"[\w가-힣]+", memory_text.lower()))
    query_tokens = set(re.findall(r"[\w가-힣]+", query.lower()))
    if not query_tokens:
        return 0.5
    overlap = len(mem_tokens & query_tokens)
    return min(overlap / max(len(query_tokens), 1), 1.0)


# ── 종합 점수 ────────────────────────────────────────────────
def _retrieval_score(
    memory: MemoryEntry,
    query: str,
    current_turn: int,
    llm: GenerativeAgentsLLM,
    alpha: float = ALPHA,
    beta: float = BETA,
    gamma: float = GAMMA,
) -> float:
    rec = _recency_score(memory, current_turn)
    imp = _importance_score(memory)
    rel = _relevance_score_llm(memory.description, query, llm)
    return alpha * rec + beta * imp + gamma * rel


# ── 공개 API ─────────────────────────────────────────────────
def retrieve_memories(
    npc_memory: dict[str, Any],
    query: str,
    llm: GenerativeAgentsLLM,
    current_turn: int,
    k: int = DEFAULT_K,
) -> list[MemoryEntry]:
    """NPC의 Memory Stream에서 query에 가장 관련 높은 k개 기억 반환.

    Args:
        npc_memory: NPCState.memory dict (이전의 npc_extras)
    """
    stream = get_memory_stream(npc_memory)
    if not stream:
        return []

    scored = [(m, _retrieval_score(m, query, current_turn, llm)) for m in stream]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [m for m, _ in scored[:k]]

    # last_access_turn 갱신
    for m in top:
        m.last_access_turn = current_turn

    logger.debug(f"retrieve_memories: query='{query[:30]}...' returned {len(top)} memories")
    return top


# ── Importance 채점 ──────────────────────────────────────────
def score_importance(
    description: str,
    npc_name: str,
    persona_summary: str,
    llm: GenerativeAgentsLLM,
) -> float:
    """기억의 중요도를 LLM으로 채점 (1‑10). fallback은 규칙 기반."""
    if not llm.available:
        return _score_importance_rule(description)

    prompt = (
        "다음 기억의 중요도를 1~10 정수로만 답하세요.\n"
        "1 = 일상적이고 사소함, 10 = 매우 중요하고 결정적임\n\n"
        f'기억: "{description}"\n'
        f"NPC: {npc_name} ({persona_summary})\n\n"
        "중요도 점수:"
    )
    resp = llm.generate(prompt, max_tokens=5, temperature=0.1)
    score = extract_number(resp, default=5.0)
    return min(max(score, 1.0), 10.0)


def _score_importance_rule(description: str) -> float:
    """규칙 기반 중요도 (LLM 없을 때 fallback)."""
    score = 5.0
    high_keywords = ["범인", "증거", "살인", "죽", "비밀", "고백", "폭로", "발견"]
    mid_keywords = ["의심", "질문", "대화", "조사", "계획"]
    for kw in high_keywords:
        if kw in description:
            score = max(score, 8.0)
    for kw in mid_keywords:
        if kw in description:
            score = max(score, 6.0)
    return score
