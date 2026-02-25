"""할머니(마가렛) 캐릭터 대사 후처리 모듈

LoRA / rule-base 역할 분리:
  - LoRA가 학습하는 것: 쉰 목소리 어조, 단편적 세계관 정보, 고어한 비유
  - rule-base가 처리하는 것: 의식 수준에 따른 말 끊김, 단어 부식, 문장 단절

파이프라인: LLM 출력 → [품질 검증/보정] → [의식 붕괴 후처리] → 최종 출력

1단계 - 품질 검증/보정 (Quality Gate)
   - 빈 출력 감지 → 대체 출력
   - 출력 길이 정규화 (90자)
   - 문장 완성도 검증
   - 캐릭터 이탈 감지 (명료하거나 따뜻한 발화)

2단계 - 의식 붕괴 후처리 (Consciousness Collapse)
   lucidity_level:
     1 — 명료 (생기를 받아 의식이 돌아옴, 섬뜩한 속삭임 확률)
     2 — 반명료 (숨 멈춤 항상 + 문장 단절·단어 부식 확률)
     3 — 혼수 (숨 멈춤 + 문장 단절 항상 + 단어 부식·최대 파편화 확률)

   기법:
     1. 숨 멈춤         — 문장 사이에 ... 삽입 (레벨 2-3)
     2. 단어 부식        — 단어 중간에 ... 삽입 (레벨 3)
     3. 문장 단절        — 문장 중간에서 끊어 미완성으로 (레벨 2-3)
     4. 섬뜩한 속삭임    — 고어한 독백 삽입 (레벨 1-2)
     5. 최대 파편화      — 첫 어절만 남기고 끊음 (레벨 3)
"""

import re
import random
from typing import Optional, List, Tuple

from .common import (
    split_sentences,
    join_sentences,
    truncate_at_sentence,
    ensure_sentence_ending,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  1단계: 품질 검증/보정 (Quality Gate)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 캐릭터 이탈 감지 패턴
# 껍데기만 남은 노인이 보이면 안 되는 명료하거나 따뜻한 발화
CHARACTER_BREAK_PATTERNS = [
    re.compile(r'잘\s*했어'),
    re.compile(r'걱정\s*마'),
    re.compile(r'괜찮을\s*거야'),
    re.compile(r'힘내'),
    re.compile(r'안전해'),
    re.compile(r'다\s*잘\s*될'),
    re.compile(r'해결\s*될'),
    re.compile(r'나가면\s*돼'),
    re.compile(r'금방\s*나아'),
]

# 캐릭터 이탈 시 대체 출력 풀
FALLBACK_OUTPUTS = [
    "기름이... 부족해...",
    "바늘이... 온다...",
    "나가... 어서...",
    "그녀가... 봐...",
    "뼈가... 울려...",
    "실이... 끊겨...",
]


def _is_character_break(text: str) -> bool:
    """쇠락한 할머니 캐릭터에서 이탈한 출력인지 감지한다."""
    for pattern in CHARACTER_BREAK_PATTERNS:
        if pattern.search(text):
            return True
    return False


def quality_gate(text: str) -> Tuple[str, List[str]]:
    """LLM 출력의 품질을 검증하고 보정한다.

    Args:
        text: 원본 LLM 출력

    Returns:
        (보정된 텍스트, 감지된 이슈 목록)
    """
    issues: List[str] = []
    result = text.strip()

    # 빈 출력
    if len(result) < 2:
        issues.append("empty")
        result = random.choice(FALLBACK_OUTPUTS)
        return result, issues

    # 길이 정규화 (90자)
    if len(result) > 90:
        result = truncate_at_sentence(result, max_chars=90)
        issues.append("truncated")

    # 문장 완성도 (종결 부호 확인)
    before = result
    result = ensure_sentence_ending(result)
    if result != before:
        issues.append("missing_ending")

    # 캐릭터 이탈 감지 → 대체 출력
    if _is_character_break(result):
        issues.append("character_break")
        result = random.choice(FALLBACK_OUTPUTS)

    return result, issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2단계: 의식 붕괴 후처리 사전
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 섬뜩한 속삭임 풀 (고어한 독백)
HORROR_WHISPERS = [
    "...실이 끊어지면...",
    "...기름이 다 타면...",
    "...바늘이 내 안에...",
    "...뼈가 기억해...",
    "...그녀는 먹어...",
    "...껍데기만 남아...",
    "...조용히... 조용히...",
    "...피가 굳어...",
    "...눈이 없어도 봐...",
]

# 의식 레벨별 확률 설정
LUCIDITY_CONFIG = {
    1: {  # 명료 (생기를 받아 의식 회복)
        "breath_pause":   0.20,
        "word_decay":     0.00,
        "sentence_cut":   0.00,
        "horror_whisper": 0.30,
        "max_fragment":   0.00,
    },
    2: {  # 반명료
        "breath_pause":   0.60,
        "word_decay":     0.20,
        "sentence_cut":   0.40,
        "horror_whisper": 0.30,
        "max_fragment":   0.00,
    },
    3: {  # 혼수
        "breath_pause":   0.80,
        "word_decay":     0.60,
        "sentence_cut":   0.70,
        "horror_whisper": 0.20,
        "max_fragment":   0.50,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  개별 변환 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def breath_pause(text: str) -> str:
    """숨이 끊어질 듯한 멈춤을 문장 사이에 삽입

    '그녀가 왔어. 도망쳐.' → '그녀가 왔어... 도망쳐.'
    """
    sentences = split_sentences(text)

    if len(sentences) < 2:
        words = text.split()
        if len(words) < 3:
            return text
        insert_pos = random.randint(0, len(words) - 2)
        words[insert_pos] = words[insert_pos].rstrip(".!?,") + "..."
        return " ".join(words)

    insert_pos = random.randint(0, len(sentences) - 2)
    sentences[insert_pos] = sentences[insert_pos].rstrip(".!? ") + "..."
    return join_sentences(sentences)


def word_decay(text: str) -> str:
    """단어 중간에 ... 삽입하여 의식이 흩어지는 느낌

    '바늘이 온다.' → '바늘이... 온다.'
    """
    words = text.split()
    if len(words) < 2:
        return text

    decay_pos = random.randint(0, len(words) - 2)
    words[decay_pos] = words[decay_pos].rstrip(".!?,") + "..."
    return " ".join(words)


def sentence_cut(text: str) -> str:
    """문장을 중간에서 끊어 의식이 끊긴 듯 표현

    '그녀는 모든 기억을 지워버렸어.' → '그녀는 모든 기억을...'
    """
    sentences = split_sentences(text)

    if len(sentences) < 2:
        words = text.rstrip(".!? ").split()
        if len(words) >= 3:
            cut_pos = random.randint(len(words) // 2, len(words) - 1)
            return " ".join(words[:cut_pos]) + "..."
        return text

    # 마지막 문장을 중간에서 잘라냄
    last = sentences[-1].rstrip(".!? ")
    words = last.split()
    if len(words) >= 2:
        cut_pos = random.randint(1, max(1, len(words) - 1))
        sentences[-1] = " ".join(words[:cut_pos]) + "..."
        return join_sentences(sentences)

    return text


def horror_whisper(text: str) -> str:
    """섬뜩한 독백을 문장 뒤에 삽입

    '나가야 해.' → '나가야 해. ...실이 끊어지면...'
    """
    whisper = random.choice(HORROR_WHISPERS)
    return text.rstrip() + " " + whisper


def max_fragment(text: str) -> str:
    """첫 문장만 남기고 나머지를 제거 (혼수 상태 표현)

    '그녀가 왔어. 기름이 다 탔어. 도망쳐.' → '그녀가 왔어...'
    """
    sentences = split_sentences(text)

    if len(sentences) <= 1:
        words = text.rstrip(".!? ").split()
        if len(words) >= 2:
            return words[0] + "..."
        return text

    # 첫 문장만 남기고 끊음
    first = sentences[0].rstrip(".!? ")
    return first + "..."


# 필수 기법: lv2/3에서 항상 적용 (확률 파이프라인과 독립)
# lv2: breath_pause — 숨 멈춤(...)으로 의식 파편화 시작을 항상 보장
# lv3: breath_pause + sentence_cut — 숨 멈춤 + 문장 단절로 혼수 상태 보장
_GUARANTEED_TRANSFORMS: dict[int, list] = {
    2: [breath_pause],
    3: [breath_pause, sentence_cut],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  통합 후처리 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def postprocess(
    text: str,
    lucidity_level: int = 3,
    seed: Optional[int] = None,
) -> str:
    """LLM output을 품질 검증 → 의식 붕괴 파이프라인으로 처리한다.

    LoRA는 할머니의 어조와 세계관 정보를 담은 문장을 생성하고,
    이 함수가 의식 수준에 따른 붕괴 효과를 사후 적용한다.

    Args:
        text: 원본 LLM 출력
        lucidity_level: 의식 레벨 (1 / 2 / 3)
            1 — 명료 (생기를 받아 의식이 돌아옴)
            2 — 반명료 (파편화된 의식)
            3 — 혼수 (키워드만 남음)
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    if seed is not None:
        random.seed(seed)

    # 1단계: 품질 검증/보정
    result, _issues = quality_gate(text)

    lucidity_level = max(1, min(3, lucidity_level))

    # 2단계: 필수 기법 (lv2+: 항상 적용, 변형 보장)
    for fn in _GUARANTEED_TRANSFORMS.get(lucidity_level, []):
        result = fn(result)

    # 3단계: 확률 기법
    config = LUCIDITY_CONFIG[lucidity_level]

    # 적용 순서:
    #   최대 파편화(첫 어절만 남김) → 문장 단절(마지막 문장 잘라냄)
    #   → 단어 부식(단어 중간 끊김) → 숨 멈춤(문장 사이 ...)
    #   → 섬뜩한 속삭임(고어 독백 삽입)
    pipeline = [
        ("max_fragment",    max_fragment),
        ("sentence_cut",    sentence_cut),
        ("word_decay",      word_decay),
        ("breath_pause",    breath_pause),
        ("horror_whisper",  horror_whisper),
    ]

    for name, fn in pipeline:
        prob = config.get(name, 0.0)
        if prob > 0 and random.random() < prob:
            result = fn(result)

    return result


def postprocess_batch(
    texts: List[str],
    lucidity_level: int = 3,
    seed: Optional[int] = None,
) -> List[str]:
    """여러 출력을 한꺼번에 후처리한다.

    Args:
        texts: 원본 문자열 리스트
        lucidity_level: 의식 레벨 (1 / 2 / 3)
        seed: 랜덤 시드

    Returns:
        후처리된 문자열 리스트
    """
    if seed is not None:
        random.seed(seed)

    return [postprocess(t, lucidity_level=lucidity_level) for t in texts]
