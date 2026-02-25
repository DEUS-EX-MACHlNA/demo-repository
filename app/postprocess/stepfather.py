"""새아빠(아더) 캐릭터 대사 후처리 모듈

LoRA / rule-base 역할 분리:
  - LoRA가 학습하는 것: 군대식/사무적 말투, 단답형 응답, 차갑고 딱딱한 톤
  - rule-base가 처리하는 것: 기억 혼란 효과, 명령 강화, 침묵 처리

파이프라인: LLM 출력 → [품질 검증/보정] → [억압 후처리] → 최종 출력

1단계 - 품질 검증/보정 (Quality Gate)
   - 빈 출력 감지 → 대체 출력
   - 출력 길이 정규화 (100자)
   - 문장 완성도 검증
   - 캐릭터 이탈 감지 (따뜻하거나 감정적인 발화)

2단계 - 억압 후처리 (Suppression Post-Processing)
   suppression_level:
     1 — 기억 혼란 (humanity 높음 — 과거 기억이 새어 나옴, 기억 파편 확률)
     2 — 냉정한 통제 (명령형 강화 항상 + 문장 압축·침묵 확률)
     3 — 완전 로봇화 (명령형 강화 + 문장 압축 항상 + 침묵 확률)

   기법:
     1. 기억 파편 삽입   — 과거 기억이 새어 나오다 억제됨 (레벨 1)
     2. 말 끊김         — 기억 혼란으로 인한 침묵 삽입 (레벨 1)
     3. 명령 강화        — 문장 끝을 더 딱딱한 명령형으로 변환 (레벨 3)
     4. 문장 압축        — 긴 문장을 한 마디 명령으로 축약 (레벨 3)
     5. 침묵 처리        — 마지막 문장을 잘라 말없이 끊어버림 (레벨 2-3)
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
# 차갑고 군대식인 새아빠가 보이면 안 되는 따뜻하고 감정적인 발화
CHARACTER_BREAK_PATTERNS = [
    re.compile(r'사랑해'),
    re.compile(r'많이\s*힘들었'),
    re.compile(r'미안해.*정말'),
    re.compile(r'네\s*편이야'),
    re.compile(r'잘\s*할\s*수\s*있'),
    re.compile(r'응원'),
    re.compile(r'자유롭게\s*해도'),
    re.compile(r'걱정\s*하지\s*마'),
    re.compile(r'괜찮아\??\s*많이'),
]

# 캐릭터 이탈 시 대체 출력 풀 (딱딱한 군대식)
FALLBACK_OUTPUTS = [
    "가만히 있어.",
    "신경 꺼.",
    "질문하지 마.",
    "따라와.",
    "그만해.",
    "됐어.",
]


def _is_character_break(text: str) -> bool:
    """냉정한 새아빠 캐릭터에서 이탈한 출력인지 감지한다."""
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

    # 길이 정규화 (군대식 단답 — 100자 기준)
    if len(result) > 100:
        result = truncate_at_sentence(result, max_chars=100)
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
#  2단계: 억압 후처리 키워드·패턴 사전
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 기억 파편 풀 (과거가 새어나왔다가 억제됨)
MEMORY_FRAGMENTS = [
    "...아니, 됐다.",
    "...그건 중요하지 않아.",
    "...예전에는... 됐어.",
    "...그때랑은 달라.",
    "...잊어.",
    "...상관없어.",
    "...아니야.",
]

# 명령 압축 규칙 (긴 문장 → 핵심 명령어)
COMPRESS_RULES = [
    ("들어가", ["들어가.", "방으로 가.", "안으로."]),
    ("나가", ["나가.", "가."]),
    ("안 돼", ["안 돼.", "안 된다.", "그만."]),
    ("기다려", ["기다려.", "거기 있어."]),
    ("조용히", ["조용히 해.", "조용.", "시끄러."]),
    ("따라", ["따라와.", "따라."]),
    ("멈춰", ["멈춰.", "서."]),
    ("앉아", ["앉아.", "거기 있어."]),
]

# 억압 레벨별 확률 설정
SUPPRESSION_CONFIG = {
    1: {  # 기억 혼란 (humanity 높음 — 인간성 표출)
        "memory_fragment":   0.60,
        "add_hesitation":    0.40,
        "order_intensify":   0.00,
        "compress_sentence": 0.00,
        "silent_drop":       0.00,
    },
    2: {  # 냉정한 통제 (기본, 변형 최소)
        "memory_fragment":   0.00,
        "add_hesitation":    0.10,
        "order_intensify":   0.20,
        "compress_sentence": 0.10,
        "silent_drop":       0.10,
    },
    3: {  # 완전 로봇화 (humanity 낮음)
        "memory_fragment":   0.00,
        "add_hesitation":    0.00,
        "order_intensify":   0.50,
        "compress_sentence": 0.45,
        "silent_drop":       0.25,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  개별 변환 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def memory_fragment(text: str) -> str:
    """과거 기억 파편을 문장 뒤에 삽입했다가 억제된 것처럼 처리

    '가만히 있어.' → '가만히 있어. ...예전에는... 됐어.'
    """
    fragment = random.choice(MEMORY_FRAGMENTS)
    return text.rstrip() + " " + fragment


def add_hesitation(text: str) -> str:
    """기억 혼란으로 인한 말 끊김 삽입

    '방에 들어가라.' → '방에... 들어가라.'
    """
    words = text.split()
    if len(words) < 3:
        return text

    insert_pos = random.randint(0, min(1, len(words) - 2))
    word = words[insert_pos].rstrip(".,!?")
    words[insert_pos] = word + "..."

    return " ".join(words)


def order_intensify(text: str) -> str:
    """어미를 더 딱딱한 명령형으로 변환

    '방에 있어도 돼.' → '방에 있어.'
    """
    sentences = split_sentences(text)
    if not sentences:
        return text

    last = sentences[-1]
    last = (last
            .replace("어도 돼.", "어.")
            .replace("면 돼.", "어.")
            .replace("해줘.", "해.")
            .replace("줄게.", ".")
            .replace("볼게.", ".")
            .replace("하세요.", "해.")
            .replace("겠어요.", "겠어."))
    sentences[-1] = last
    return join_sentences(sentences)


def compress_sentence(text: str) -> str:
    """긴 문장을 핵심 명령 한 마디로 압축"""
    sentences = split_sentences(text)
    if len(sentences) < 2:
        return text

    last = sentences[-1]
    for keyword, replacements in COMPRESS_RULES:
        if keyword in last:
            sentences[-1] = random.choice(replacements)
            return join_sentences(sentences)

    # 폴백: 마지막 문장만 남김
    return sentences[-1] if sentences else text


def silent_drop(text: str) -> str:
    """마지막 문장을 제거하여 말없이 끊어버리는 느낌

    '어디 가는 거야. 방으로 가.' → '어디 가는 거야.'
    """
    sentences = split_sentences(text)
    if len(sentences) > 1:
        return join_sentences(sentences[:-1])
    return text


# 필수 기법: lv2/3에서 항상 적용 (확률 파이프라인과 독립)
# lv2: order_intensify — 어미를 딱딱한 명령형으로 항상 변환 (냉정함 보장)
# lv3: order_intensify + compress_sentence — 명령형 + 핵심 명령 압축으로 로봇화 보장
_GUARANTEED_TRANSFORMS: dict[int, list] = {
    2: [order_intensify],
    3: [order_intensify, compress_sentence],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  통합 후처리 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def postprocess(
    text: str,
    suppression_level: int = 2,
    seed: Optional[int] = None,
) -> str:
    """LLM output을 품질 검증 → 억압 후처리 파이프라인으로 처리한다.

    Args:
        text: 원본 LLM 출력
        suppression_level: 억압 단계 (1 / 2 / 3)
            1 — 기억 혼란 (humanity가 높아 과거가 새어 나옴)
            2 — 냉정한 통제 (기본, 변형 최소)
            3 — 완전 로봇화 (humanity가 낮아 명령만 남음)
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    if seed is not None:
        random.seed(seed)

    # 1단계: 품질 검증/보정
    result, _issues = quality_gate(text)

    suppression_level = max(1, min(3, suppression_level))

    # 2단계: 필수 기법 (lv2+: 항상 적용, 변형 보장)
    for fn in _GUARANTEED_TRANSFORMS.get(suppression_level, []):
        result = fn(result)

    # 3단계: 확률 기법
    config = SUPPRESSION_CONFIG[suppression_level]

    # 적용 순서:
    #   문장 압축(기저 텍스트 단순화) → 명령 강화(어미 변환)
    #   → 말 끊김(... 삽입) → 기억 파편(과거 새어 나옴)
    #   → 침묵 처리(끊어버림)
    pipeline = [
        ("compress_sentence",  compress_sentence),
        ("order_intensify",    order_intensify),
        ("add_hesitation",     add_hesitation),
        ("memory_fragment",    memory_fragment),
        ("silent_drop",        silent_drop),
    ]

    for name, fn in pipeline:
        prob = config.get(name, 0.0)
        if prob > 0 and random.random() < prob:
            result = fn(result)

    return result


def postprocess_batch(
    texts: List[str],
    suppression_level: int = 2,
    seed: Optional[int] = None,
) -> List[str]:
    """여러 출력을 한꺼번에 후처리한다.

    Args:
        texts: 원본 문자열 리스트
        suppression_level: 억압 단계 (1 / 2 / 3)
        seed: 랜덤 시드

    Returns:
        후처리된 문자열 리스트
    """
    if seed is not None:
        random.seed(seed)

    return [postprocess(t, suppression_level=suppression_level) for t in texts]
