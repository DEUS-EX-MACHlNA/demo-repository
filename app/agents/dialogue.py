"""
app/agents/dialogue.py
NPC간 대화 생성 — Generative Agents (Park et al. 2023) Section 3.5

두 NPC가 관련 기억을 검색하고, 페르소나에 맞는 발화를 교대로 생성한다.
대화 후 감정 변화를 분석한다.
"""
from __future__ import annotations

import json
import logging
import random
import re
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
def generate_utterance(
    speaker_id: str,
    speaker_name: str,
    speaker_persona: dict[str, Any],
    speaker_memory: dict[str, Any],
    speaker_stats: dict[str, int],
    listener_name: str,
    conversation_history: list[dict[str, str]],
    llm: GenerativeAgentsLLM,
    current_turn: int = 1,
    world_snapshot: dict[str, Any] | None = None,
) -> str:
    """단일 발화 생성.

    Args:
        speaker_memory: NPCState.memory dict
        speaker_stats: NPC 스탯 Dict (예: {"affection": 50, "humanity": 0})
        world_snapshot: 월드 상태 요약 dict (None이면 간단 프롬프트 사용)
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

    if world_snapshot:
        humanity = speaker_stats.get("humanity", 100)
        prompt = _build_rich_utterance_prompt(
            speaker_id, speaker_name, speaker_persona, persona_str, emotion_str,
            plan_text, mem_ctx, history, listener_name, world_snapshot,
            humanity=humanity,
        )
    else:
        # 폴백: 간단 프롬프트
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

    resp = llm.generate(prompt=prompt, max_tokens=80, npc_id=speaker_id)
    if not resp:
        resp = f"...{speaker_name}은(는) 잠시 말을 아꼈다."
    return resp.strip()


_HUMANITY_DIRECTIVES: dict[str, dict[int, str]] = {
    "stepmother": {
        1: "차분하고 통제적. 달콤하지만 은근한 위협. 완벽주의적 규율 강조.",
        2: "불안정 시작. 달콤함과 날카로움이 공존. 가끔 말이 반복되거나 과도해짐.",
        3: "광기적 집착. 감정이 달콤함↔분노로 폭발적 급변. 말이 끊기거나 반복 과다. 은근함 없이 직접적 집착/위협.",
    },
    "stepfather": {
        1: "규칙을 강조하되 인간적 기억 흔적이 새어나옴. 가끔 과거 감정이 드러남.",
        2: "냉정하고 명령적. 감정 절제. 짧고 단호한 지시 위주.",
        3: "완전 기계적. 극도로 짧은 명령형 문장. 감정 일절 없음. 규칙과 지시만 반복.",
    },
    "grandmother": {
        1: "의식 또렷. 따뜻하지만 가끔 공포스러운 진실을 말함.",
        2: "반명료. 문장을 완성하기 어려움. 과거와 현재가 뒤섞임.",
        3: "혼수 상태. 단편적 단어 나열. 문장 불완전. 의미 불분명한 단어들.",
    },
    "brother": {
        1: "정상적인 5세 아이. 애정을 갈구하고 외로워함. 자연스러운 아이 말투.",
        2: "혼란. 말을 더듬고 같은 단어를 반복. 가끔 자신을 3인칭으로 부름.",
        3: "인형화. 감정 없이 평탄하게 말함. '나' 대신 '이 아이' 또는 3인칭 사용. 느낌표 없음.",
    },
    "dog_baron": {
        1: "우호적이고 활발. 꼬리 흔드는 이미지. 플레이어에게 친밀하게 반응.",
        2: "경계적·주저함. 조심스럽게 접근. 머뭇거리는 반응.",
        3: "적대적. 으르렁거리며 위협. 접근 거부. 공격적 행동 묘사.",
    },
}

_HUMANITY_DEFAULT: dict[int, str] = {
    1: "자연스러운 기본 반응.",
    2: "다소 경직되거나 불안한 반응.",
    3: "극도로 위협적이거나 단절된 반응.",
}

_HUMANITY_LEVEL_LABELS = {1: "정상", 2: "중간", 3: "극단"}


def _build_humanity_directive(npc_id: str, humanity: int) -> str:
    """humanity 수치를 레벨로 변환해 NPC별 행동 지침 문자열 반환.

    레벨 매핑 (postprocess/__init__.py의 humanity_to_level과 동일):
        ≥ 70  → 레벨 1 (정상)
        40~69 → 레벨 2 (중간)
        < 40  → 레벨 3 (극단)
    """
    if humanity >= 70:
        level = 1
    elif humanity >= 40:
        level = 2
    else:
        level = 3

    directives = _HUMANITY_DIRECTIVES.get(npc_id, _HUMANITY_DEFAULT)
    label = _HUMANITY_LEVEL_LABELS[level]
    guide = directives[level]
    return f"humanity={humanity} → {label} 상태. {guide}"


def _build_rich_utterance_prompt(
    speaker_id: str,
    speaker_name: str,
    speaker_persona: dict[str, Any],
    persona_str: str,
    emotion_str: str,
    plan_text: str,
    mem_ctx: str,
    history: str,
    listener_name: str,
    ws: dict[str, Any],
    humanity: int = 100,
) -> str:
    """world_snapshot이 있을 때 사용하는 구체화된 NPC 발화 프롬프트."""
    genre = ws.get("genre", "")
    tone = ws.get("tone", "")

    # 트리거/금기 추출
    triggers = speaker_persona.get("triggers", {})
    triggers_plus = ", ".join(triggers.get("plus", [])) or "(없음)"
    triggers_minus = ", ".join(triggers.get("minus", [])) or "(없음)"
    raw_taboos = speaker_persona.get("taboos", "")
    taboos = raw_taboos if isinstance(raw_taboos, str) else ", ".join(raw_taboos) if raw_taboos else "(없음)"
    if not taboos:
        taboos = "(없음)"

    # 관계 정보
    relationships = speaker_persona.get("relationships", "")
    relationships_str = relationships if isinstance(relationships, str) else ", ".join(relationships) if relationships else "(없음)"
    if not relationships_str:
        relationships_str = "(없음)"

    # flags 요약 (true인 것만)
    flags = ws.get("flags", {})
    flags_summary = ", ".join(f"{k}={v}" for k, v in flags.items() if v) if flags else "(없음)"

    # 인벤토리
    inventory = ", ".join(ws.get("inventory", [])) or "(없음)"

    humanity_directive = _build_humanity_directive(speaker_id, humanity)

    return (
        f"[ROLE]\n"
        f"너는 NPC \"{speaker_name}\"이다. 장르는 '{genre}'. {tone}.\n"
        f"과장된 소설체 금지. 너의 목표: (a) 캐릭터성 유지 (b) 규칙 준수 (c) 1~2문장 반응.\n\n"
        f"[ABSOLUTE RULES]\n"
        f"- 새로운 사실/새 탈출구/새 인물 생성 금지. (확정된 세계관/상태만 사용)\n"
        f"- 아래 '금기(taboos)'를 위반하는 발화는 피하거나 돌려 말해라.\n"
        f"- 결과/판정/서술은 하지 말고 \"대사\"만 말해라.\n\n"
        f"[NPC PROFILE]\n"
        f"페르소나: {persona_str}\n"
        f"관계: {relationships_str}\n"
        f"금기(taboos): {taboos}\n"
        f"트리거(+): {triggers_plus}\n"
        f"트리거(-): {triggers_minus}\n"
        f"현재 감정: {emotion_str}\n"
        f"현재 계획(단기): {plan_text}\n"
        f"스탯 반영 가이드:\n"
        f"- fear↑: 더 집착/불안/통제\n"
        f"- affection↓: 더 차갑고 거리감\n\n"
        f"[현재 상태 가이드]\n"
        f"{humanity_directive}\n\n"
        f"[WORLD SNAPSHOT]\n"
        f"day={ws.get('day', 1)}, turn={ws.get('turn', 1)}, "
        f"suspicion_level={ws.get('suspicion_level', 0)}, "
        f"player_humanity={ws.get('player_humanity', 100)}\n"
        f"flags={flags_summary}\n"
        f"현재 장소: {ws.get('node_id', 'unknown')}\n"
        f"플레이어 인벤토리: {inventory}\n\n"
        f"[MEMORY]\n"
        f"{mem_ctx}\n\n"
        f"[RECENT DIALOGUE]\n"
        f"{history}\n\n"
        f"[YOUR TASK]\n"
        f"\"{listener_name}\"에게 지금 무엇을 말할지 결정하고 말하라.\n"
        f"- 1~2문장, 자연스럽고 간결.\n"
        f"- 트리거(plus/minus)와 금기(taboos)를 고려.\n"
        f"- 의심도가 높으면: 더 확인 질문/견제/감시 톤 강화.\n\n"
        f"발화:"
    )


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
        u1 = generate_utterance(
            npc1_id, npc1_name, npc1_persona, npc1_memory,
            npc1_stats,
            npc2_name, conversation, llm, current_turn,
        )
        conversation.append({"speaker": npc1_name, "text": u1})

        # NPC2 발화
        u2 = generate_utterance(
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
    hits_info: dict[str, int] | None = None,
) -> None:
    """대화 내용을 해당 NPC의 Memory Stream에 dialogue 기억으로 저장.

    Args:
        npc_memory: NPCState.memory dict (이전의 npc_extras)
        hits_info: 낮 대화 영향 분석의 plus/minus hits (밤에는 None)
    """
    # 상대 발화를 요약하여 저장
    other_utterances = [c["text"] for c in conversation if c["speaker"] == other_name]
    summary = f"{other_name}와(과) 대화함. 상대 발언: " + "; ".join(other_utterances[:3])
    if len(summary) > 200:
        summary = summary[:197] + "..."

    imp = score_importance(summary, npc_name, persona_summary, llm, hits_info=hits_info)
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
    world_context: dict[str, Any] | None = None,
    include_triggers: bool = False,
) -> dict[str, Any]:
    """대화가 양측 감정에 미친 영향 분석.

    Args:
        stat_names: 분석할 스탯 이름 리스트 (예: ["affection", "humanity"])
                    None이면 자동 감지
        world_context: 분석에 참고할 월드 컨텍스트 (suspicion_level, player_humanity 등)
        include_triggers: True이면 플레이어 트리거 판별 + hits 반환 (낮 페이즈용)

    Returns:
        {
            "npc_stats": {npc_id: {stat: delta(-2~+2), ...}},
            "event_description": ["핵심 사건 묘사"]
        }
        include_triggers=True일 때 npc_stats에 plus_hits, minus_hits 포함.
    """
    conv_text = "\n".join(f"{c['speaker']}: {c['text']}" for c in conversation)
    p1 = format_persona(npc1_persona)
    p2 = format_persona(npc2_persona)

    # 동적 스탯 이름으로 프롬프트 생성
    if stat_names:
        stat_list_str = ", ".join(stat_names)
        stat_example = ", ".join(f'"{s}": 0' for s in stat_names)
    else:
        stat_list_str = "각 스탯"
        stat_example = '"stat1": 0, "stat2": 0'

    # 트리거 추출 (항상 포함 — 스탯 변화 판단에 필요)
    t1 = npc1_persona.get("triggers", {})
    triggers_plus_1 = ", ".join(t1.get("plus", [])) or "(없음)"
    triggers_minus_1 = ", ".join(t1.get("minus", [])) or "(없음)"

    t2 = npc2_persona.get("triggers", {})
    triggers_plus_2 = ", ".join(t2.get("plus", [])) or "(없음)"
    triggers_minus_2 = ", ".join(t2.get("minus", [])) or "(없음)"

    npc1_section = (
        f"[NPC1: {npc1_name}]\n"
        f"페르소나: {p1}\n"
        f"트리거(+): {triggers_plus_1}  (이 행동이 있으면 스탯 상승)\n"
        f"트리거(-): {triggers_minus_1}  (이 행동이 있으면 스탯 하락)\n"
    )
    npc2_section = (
        f"[NPC2: {npc2_name}]\n"
        f"페르소나: {p2}\n"
        f"트리거(+): {triggers_plus_2}  (이 행동이 있으면 스탯 상승)\n"
        f"트리거(-): {triggers_minus_2}  (이 행동이 있으면 스탯 하락)\n"
    )

    # hits 카운팅은 낮(플레이어 행동)에서만 적용
    if include_triggers:
        hits_example = ', "plus_hits": 0, "minus_hits": 0'
        triggers_rules = (
            f"- 플레이어 발화/행동이 트리거에 해당하는지 판별:\n"
            f"  - plus 트리거 해당 → plus_hits: 1\n"
            f"  - minus 트리거 해당 → minus_hits: 1\n"
            f"  - 해당 없으면 각각 0\n"
        )
    else:
        hits_example = ""
        triggers_rules = ""

    # world_context 섹션
    context_section = ""
    if world_context:
        context_section = (
            f"\n[CONTEXT]\n"
            f"suspicion_level={world_context.get('suspicion_level', 0)}, "
            f"player_humanity={world_context.get('player_humanity', 100)}\n"
        )

    prompt = (
        f"[TASK] 아래 대화를 분석하여 NPC 감정 변화(stat delta)와 핵심 사건을 추출하세요.\n\n"
        f"[CONVERSATION]\n{conv_text}\n\n"
        f"{npc1_section}\n"
        f"{npc2_section}"
        f"{context_section}\n"
        f"[RULES]\n"
        f"- 각 인물의 {stat_list_str} 변화를 -2~+2 범위의 **델타값**으로 판정.\n"
        f"{triggers_rules}"
        f"- event_description: 핵심 사건 1~2문장.\n\n"
        f"[OUTPUT - JSON ONLY]\n"
        "```json\n"
        "{\n"
        f'  "npc_stats": {{\n'
        f'    "{npc1_id}": {{{stat_example}{hits_example}}},\n'
        f'    "{npc2_id}": {{{stat_example}{hits_example}}}\n'
        f"  }},\n"
        '  "event_description": ["핵심 사건 묘사"]\n'
        "}\n"
        "```"
    )
    resp = llm.generate(prompt=prompt, max_tokens=200, temperature=0.3)

    result = _parse_impact_response(resp, npc1_id, npc1_name, npc2_id, npc2_name, stat_names, include_triggers)
    logger.debug(f"conversation_impact: {result}")
    return result


def _parse_impact_response(
    resp: str,
    npc1_id: str,
    npc1_name: str,
    npc2_id: str,
    npc2_name: str,
    stat_names: list[str] | None,
    include_triggers: bool = False,
) -> dict[str, Any]:
    """analyze_conversation_impact의 LLM 응답을 파싱."""
    fallback: dict[str, Any] = {
        "npc_stats": {npc1_id: {}, npc2_id: {}},
        "event_description": [],
    }
    if not resp:
        return fallback

    # JSON 블록 추출
    json_match = re.search(r'```json\s*(.*?)\s*```', resp, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r'\{.*\}', resp, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            # JSON 파싱 실패 시 기존 텍스트 파싱으로 폴백
            logger.warning(f"[analyze_impact] JSON 파싱 실패, 텍스트 파싱 시도: {resp[:100]}")
            logger.info(f"[analyze_impact] 원본 LLM 응답 : {resp}")
            return _parse_impact_text_fallback(resp, npc1_id, npc1_name, npc2_id, npc2_name, stat_names)

    try:
        data = json.loads(json_str)
        npc_stats = data.get("npc_stats", {})
        event_description = data.get("event_description", [])

        hits_keys = {"plus_hits", "minus_hits"}
        for npc_id in [npc1_id, npc2_id]:
            if npc_id in npc_stats:
                clamped = {}
                for k, v in npc_stats[npc_id].items():
                    # 밤 페이즈에서는 hits 키 무시
                    if k in hits_keys and not include_triggers:
                        continue
                    try:
                        iv = int(v)
                    except (ValueError, TypeError):
                        iv = 0
                    if k in hits_keys:
                        clamped[k] = max(0, min(1, iv))
                    else:
                        clamped[k] = max(-2, min(2, iv))
                npc_stats[npc_id] = clamped
            else:
                npc_stats[npc_id] = {}

        if isinstance(event_description, str):
            event_description = [event_description]

        return {
            "npc_stats": npc_stats,
            "event_description": event_description,
        }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[analyze_impact] JSON 디코드 실패: {e}, 텍스트 파싱 시도")
        logger.info(f"[analyze_impact] 원본 LLM 응답 : {resp}")
        return _parse_impact_text_fallback(resp, npc1_id, npc1_name, npc2_id, npc2_name, stat_names)


def _parse_impact_text_fallback(
    resp: str,
    npc1_id: str,
    npc1_name: str,
    npc2_id: str,
    npc2_name: str,
    stat_names: list[str] | None,
) -> dict[str, Any]:
    """JSON 파싱 실패 시 기존 텍스트 파싱 방식으로 폴백."""
    npc_stats: dict[str, dict[str, int]] = {}
    lines = resp.strip().splitlines()
    for line in lines:
        if npc1_name in line:
            npc_stats[npc1_id] = parse_stat_changes_text(line, stat_names)
        elif npc2_name in line:
            npc_stats[npc2_id] = parse_stat_changes_text(line, stat_names)

    npc_stats.setdefault(npc1_id, {})
    npc_stats.setdefault(npc2_id, {})

    return {
        "npc_stats": npc_stats,
        "event_description": [],
    }
