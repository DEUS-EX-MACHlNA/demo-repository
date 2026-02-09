"""
app/agents/dialogue.py
NPC간 대화 생성 — Generative Agents (Park et al. 2023) Section 3.5

두 NPC가 관련 기억을 검색하고, 페르소나에 맞는 발화를 교대로 생성한다.
대화 후 감정 변화를 분석한다.
"""
from __future__ import annotations

import logging
import random
from typing import Any

from app.llm import GenerativeAgentsLLM
from app.agents.memory import MEMORY_DIALOGUE, MemoryEntry, add_memory
from app.agents.retrieval import retrieve_memories, score_importance
from app.agents.utils import format_emotion, format_persona, parse_stat_changes_text

logger = logging.getLogger(__name__)

MAX_DIALOGUE_TURNS = 2  # 교환 횟수 (각 교환 = 양쪽 1발화씩)
MAX_PAIRS = 2


# ── 대화 쌍 결정 ─────────────────────────────────────────────
def determine_dialogue_pairs(
    npc_ids: list[str],
    npc_memory_map: dict[str, dict[str, Any]],
) -> list[tuple[str, str]]:
    """이번 턴에 대화할 NPC 쌍 결정.

    Args:
        npc_memory_map: {npc_id: NPCState.memory dict} 매핑 (이전의 npc_extras_map)

    현재는 단순 전략: 계획에 다른 NPC 언급이 있으면 우선, 없으면 랜덤 1쌍.
    """
    if len(npc_ids) < 2:
        return []

    pairs: list[tuple[str, str]] = []

    # 계획 기반 매칭
    for i, npc_a in enumerate(npc_ids):
        plan_text = (
            npc_memory_map.get(npc_a, {})
            .get("current_plan", {})
            .get("plan_text", "")
        )
        for npc_b in npc_ids[i + 1:]:
            if npc_b in plan_text or npc_a in npc_memory_map.get(npc_b, {}).get(
                "current_plan", {}
            ).get("plan_text", ""):
                pairs.append((npc_a, npc_b))

    # 쌍이 없으면 랜덤 1쌍
    if not pairs:
        shuffled = list(npc_ids)
        random.shuffle(shuffled)
        pairs.append((shuffled[0], shuffled[1]))

    return pairs[:MAX_PAIRS]


# ── 단일 발화 생성 ───────────────────────────────────────────
def _generate_utterance(
    speaker_id: str,
    speaker_name: str,
    speaker_persona: dict[str, Any],
    speaker_memory: dict[str, Any],
    speaker_stats: dict[str, int],
    listener_name: str,
    conversation_history: list[dict[str, str]],
    llm: GenerativeAgentsLLM,
    current_turn: int = 1,
) -> str:
    """단일 발화 생성.

    Args:
        speaker_memory: NPCState.memory dict
        speaker_stats: NPC 스탯 Dict (예: {"affection": 50, "fear": 80})
    """
    persona_str = format_persona(speaker_persona)
    emotion_str = format_emotion(speaker_stats)

    # 관련 기억 검색
    query = f"{listener_name}와(과) 대화"
    memories = retrieve_memories(speaker_memory, query, llm, current_turn=current_turn, k=3)
    mem_ctx = "\n".join(f"- {m.description}" for m in memories) if memories else "(관련 기억 없음)"

    plan_text = speaker_memory.get("current_plan", {}).get("plan_text", "")

    # 대화 이력
    history = "\n".join(f"{h['speaker']}: {h['text']}" for h in conversation_history[-4:])
    if not history:
        history = "(대화 시작)"

    prompt = (
        f"당신은 {speaker_name}입니다.\n\n"
        f"페르소나: {persona_str}\n"
        f"현재 감정: {emotion_str}\n"
        f"현재 계획: {plan_text}\n\n"
        f"관련 기억:\n{mem_ctx}\n\n"
        f"대화 기록:\n{history}\n\n"
        f"{listener_name}에게 무엇을 말하겠습니까? (자연스럽고 간결하게, 1~2문장)\n\n"
        "발화:"
    )
    resp = llm.generate(prompt, max_tokens=80)
    if not resp:
        resp = f"...{speaker_name}은(는) 잠시 말을 아꼈다."
    return resp.strip()


# ── NPC간 대화 생성 ──────────────────────────────────────────
def generate_dialogue(
    npc1_id: str,
    npc1_name: str,
    npc1_persona: dict[str, Any],
    npc1_memory: dict[str, Any],
    npc1_stats: dict[str, int],
    npc2_id: str,
    npc2_name: str,
    npc2_persona: dict[str, Any],
    npc2_memory: dict[str, Any],
    npc2_stats: dict[str, int],
    llm: GenerativeAgentsLLM,
    current_turn: int = 1,
    max_turns: int = MAX_DIALOGUE_TURNS,
) -> list[dict[str, str]]:
    """두 NPC의 대화를 생성. [{speaker, text}, ...] 반환.

    Args:
        npc1_memory, npc2_memory: NPCState.memory dict
        npc1_stats, npc2_stats: NPC 스탯 Dict
    """
    conversation: list[dict[str, str]] = []

    for _ in range(max_turns):
        # NPC1 발화
        u1 = _generate_utterance(
            npc1_id, npc1_name, npc1_persona, npc1_memory,
            npc1_stats,
            npc2_name, conversation, llm, current_turn,
        )
        conversation.append({"speaker": npc1_name, "text": u1})

        # NPC2 발화
        u2 = _generate_utterance(
            npc2_id, npc2_name, npc2_persona, npc2_memory,
            npc2_stats,
            npc1_name, conversation, llm, current_turn,
        )
        conversation.append({"speaker": npc2_name, "text": u2})

    logger.info(
        f"dialogue: {npc1_name} <-> {npc2_name}, {len(conversation)} utterances"
    )
    return conversation


# ── 대화를 기억으로 저장 ─────────────────────────────────────
def store_dialogue_memories(
    npc_id: str,
    npc_name: str,
    other_name: str,
    conversation: list[dict[str, str]],
    npc_memory: dict[str, Any],
    persona_summary: str,
    llm: GenerativeAgentsLLM,
    current_turn: int = 1,
) -> None:
    """대화 내용을 해당 NPC의 Memory Stream에 dialogue 기억으로 저장.

    Args:
        npc_memory: NPCState.memory dict (이전의 npc_extras)
    """
    # 상대 발화를 요약하여 저장
    other_utterances = [c["text"] for c in conversation if c["speaker"] == other_name]
    summary = f"{other_name}와(과) 대화함. 상대 발언: " + "; ".join(other_utterances[:3])
    if len(summary) > 200:
        summary = summary[:197] + "..."

    imp = score_importance(summary, npc_name, persona_summary, llm)
    entry = MemoryEntry.create(
        npc_id=npc_id,
        description=summary,
        importance_score=imp,
        current_turn=current_turn,
        memory_type=MEMORY_DIALOGUE,
    )
    add_memory(npc_memory, entry)


# ── 대화 영향 분석 ───────────────────────────────────────────
def analyze_conversation_impact(
    npc1_id: str,
    npc1_name: str,
    npc1_persona: dict[str, Any],
    npc2_id: str,
    npc2_name: str,
    npc2_persona: dict[str, Any],
    conversation: list[dict[str, str]],
    llm: GenerativeAgentsLLM,
    stat_names: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    """대화가 양측 NPC 감정에 미친 영향 분석. {npc_id: {stat: delta}} 반환.

    Args:
        stat_names: 분석할 스탯 이름 리스트 (예: ["affection", "fear", "humanity"])
                    None이면 자동 감지
    """
    conv_text = "\n".join(f"{c['speaker']}: {c['text']}" for c in conversation)
    p1 = format_persona(npc1_persona)
    p2 = format_persona(npc2_persona)

    # 동적 스탯 이름으로 프롬프트 생성
    if stat_names:
        stat_list_str = ", ".join(stat_names)
        example_line = ", ".join(f"{s}: 0" for s in stat_names)
    else:
        stat_list_str = "각 스탯"
        example_line = "stat1: 0, stat2: 0"

    prompt = (
        "다음 대화를 분석하여 각 인물의 감정 변화를 예측하세요.\n\n"
        f"대화:\n{conv_text}\n\n"
        f"{npc1_name} 페르소나: {p1}\n"
        f"{npc2_name} 페르소나: {p2}\n\n"
        f"각 인물의 {stat_list_str} 변화를 -2~+2 범위로 답하세요.\n\n"
        f"{npc1_name} 변화 - {example_line}\n"
        f"{npc2_name} 변화 - {example_line}"
    )
    resp = llm.generate(prompt, max_tokens=100, temperature=0.3)

    result: dict[str, dict[str, int]] = {}
    if resp:
        lines = resp.strip().splitlines()
        for line in lines:
            if npc1_name in line:
                result[npc1_id] = parse_stat_changes_text(line, stat_names)
            elif npc2_name in line:
                result[npc2_id] = parse_stat_changes_text(line, stat_names)

    # fallback: 분석 실패 시 빈 변화
    result.setdefault(npc1_id, {})
    result.setdefault(npc2_id, {})

    logger.debug(f"conversation_impact: {result}")
    return result
