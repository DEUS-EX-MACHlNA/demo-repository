"""
동생(루카스) 캐릭터 대사 후처리 모듈

LoRA / rule-base 역할 분리:
  - LoRA가 학습하는 것: 시맨틱 방향(놀아줘/같이 있어줘), 5세 어휘, 아이 말투
  - rule-base가 처리하는 것: 말 끊김, 단어 반복, 자기 지칭 혼란, 글리치 효과
  → 겹침 없이 분리하여 이중 적용 방지

파이프라인: LLM 출력 → [품질 검증/보정] → [글리치 후처리] → 최종 출력

1단계 - 품질 검증/보정 (Quality Gate)
   - 빈 출력 감지 → 대체 출력
   - 출력 길이 정규화 (80자 — 5세 아이 기준)
   - 문장 완성도 검증
   - 캐릭터 이탈 감지 (성숙한/독립적/무관심한 발화)

2단계 - 글리치 후처리 (Glitch Post-Processing)
   glitch_level:
     1 — 변형 없음 (외로운 아이)
     2 — 혼란 (인형/인간 사이 흔들림)
     3 — 인형화 (인형 본능이 지배)

   기법:
     1. 말 끊김 삽입     — 단어 사이에 ... 삽입
     2. 단어 에코        — 감정 키워드를 되뇌이듯 반복
     3. 자기 지칭 혼란   — "나"를 "이 인형" / "이 아이"로 치환
     4. 감정 플랫화      — !/?를 .으로 치환 (무감정, 인형화)
     5. 호칭 반복        — "누나" 되뇌이듯 반복
     6. 문장 단절        — 문장을 중간에서 끊어 미완성으로
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
# 5세 외로운/집착적 아이가 하지 않을 성숙·독립·무관심한 발화
CHARACTER_BREAK_PATTERNS = [
    re.compile(r'혼자.*할\s*수\s*있'),      # 독립 응원
    re.compile(r'괜찮아.*혼자'),             # 혼자 괜찮다
    re.compile(r'신경\s*쓰지?\s*마'),        # 무관심
    re.compile(r'알아서\s*해'),              # 독립적
    re.compile(r'상관\s*없'),               # 무관심
    re.compile(r'필요\s*없'),               # 거부 (집착 캐릭터가 거부하면 이탈)
    re.compile(r'가도\s*돼'),               # 떠나는 것 허용 (집착 이탈)
]

# 캐릭터 이탈 시 대체 출력 풀
FALLBACK_OUTPUTS = [
    "나랑 놀자.",
    "누나 어디 가?",
    "나 혼자 있기 싫어.",
    "가지 마.",
    "누나 나 좋아해?",
    "같이 있어줘.",
]


def _is_character_break(text: str) -> bool:
    """외로운 5세 아이 캐릭터에서 이탈한 출력인지 감지한다."""
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

    # 길이 정규화 (5세 아이: 짧게 — 80자 기준)
    if len(result) > 80:
        result = truncate_at_sentence(result, max_chars=80)
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
#  2단계: 글리치 후처리 키워드·패턴 사전
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 자기 지칭 혼란: "나+조사" → 대체어+조사 매핑
# 받침 유무에 따른 조사 변형을 직접 정의하여 정확한 한국어 처리
SELF_REPLACEMENT_MAP = {
    "이 인형": {  # '형' 받침 ㅇ → 은/이/을
        "나는": "이 인형은",
        "나도": "이 인형도",
        "나를": "이 인형을",
        "나한테": "이 인형한테",
        "내가": "이 인형이",
        "나만": "이 인형만",
    },
    "이 아이": {  # '이' 받침 없음 → 는/가/를
        "나는": "이 아이는",
        "나도": "이 아이도",
        "나를": "이 아이를",
        "나한테": "이 아이한테",
        "내가": "이 아이가",
        "나만": "이 아이만",
    },
    "루카스": {  # '스' 받침 없음 → 는/가/를
        "나는": "루카스는",
        "나도": "루카스도",
        "나를": "루카스를",
        "나한테": "루카스한테",
        "내가": "루카스가",
        "나만": "루카스만",
    },
}

# 에코 대상 감정 키워드
ECHO_KEYWORDS = [
    "놀자", "가지 마", "싫어", "무서워", "같이",
    "있어줘", "혼자", "제발", "안 돼", "좋아",
]

# 호칭
CALLING_KEYWORD = "누나"

# 글리치 레벨별 확률 설정
GLITCH_CONFIG = {
    1: {
        "stutter_pause":   0.00,
        "word_echo":       0.00,
        "self_confusion":  0.00,
        "flatten_emotion": 0.00,
        "calling_repeat":  0.00,
        "sentence_cut":    0.00,
    },
    2: {
        "stutter_pause":   0.25,
        "word_echo":       0.15,
        "self_confusion":  0.10,
        "flatten_emotion": 0.00,
        "calling_repeat":  0.10,
        "sentence_cut":    0.00,
    },
    3: {
        "stutter_pause":   0.50,
        "word_echo":       0.50,
        "self_confusion":  0.35,
        "flatten_emotion": 0.40,
        "calling_repeat":  0.35,
        "sentence_cut":    0.30,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  개별 변환 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def stutter_pause(text: str) -> str:
    """단어 사이에 ...을 삽입하여 말 끊김 표현

    LoRA 출력 '나 혼자 있기 싫어' → '나... 혼자 있기 싫어'
    """
    words = text.split()
    if len(words) < 3:
        return text

    insert_pos = random.randint(0, min(1, len(words) - 2))
    word = words[insert_pos].rstrip(".,!?")
    words[insert_pos] = word + "..."

    return " ".join(words)


def word_echo(text: str) -> str:
    """감정 키워드를 되뇌이듯 반복

    LoRA 출력 '나랑 놀자.' → '나랑 놀자... 놀자...'
    """
    for keyword in ECHO_KEYWORDS:
        if keyword in text:
            repeat_count = random.randint(1, 2)
            echo_part = " ".join([keyword + "..." for _ in range(repeat_count)])
            text = text.rstrip(".!? ") + "... " + echo_part
            break
    return text


def self_confusion(text: str) -> str:
    """'나'를 '이 인형'/'이 아이'/'루카스'로 치환하여 정체성 혼란

    LoRA 출력 '나 혼자 있기 싫어.' → '이 인형은 혼자 있기 싫어.'
    """
    replacement_key = random.choice(list(SELF_REPLACEMENT_MAP.keys()))
    mapping = SELF_REPLACEMENT_MAP[replacement_key]

    # 조사 포함 패턴 우선 매칭
    for original, replacement in mapping.items():
        if original in text:
            return text.replace(original, replacement, 1)

    # 폴백: 단독 "나 " 매칭
    if "나 " in text:
        return text.replace("나 ", replacement_key + " ", 1)

    return text


def flatten_emotion(text: str) -> str:
    """감정 부호를 제거하여 무감정/인형화 표현

    LoRA 출력 '놀아줘!' → '놀아줘.'
    LoRA 출력 '누나 화났어?' → '누나 화났어.'
    """
    text = text.replace("!", ".").replace("?", ".")
    text = re.sub(r'\.{2,}', '.', text)
    return text


def calling_repeat(text: str) -> str:
    """'누나'를 되뇌이듯 반복

    LoRA 출력 '가지 마.' → '누나... 누나... 가지 마.'
    """
    repeat_count = random.randint(2, 3)
    prefix = " ".join([CALLING_KEYWORD + "..." for _ in range(repeat_count)])

    if CALLING_KEYWORD in text:
        return prefix + " " + text
    else:
        return text.rstrip(".!? ") + ". " + prefix


def sentence_cut(text: str) -> str:
    """문장을 중간에서 끊어 미완성으로 만듦

    LoRA 출력 '나도 알고 싶어. 근데 생각하면 이상해져.'
    → '나도 알고 싶어. 근데 생각하면...'
    """
    sentences = split_sentences(text)

    if len(sentences) < 2:
        # 단문: 마지막 단어 앞에서 자름
        words = text.rstrip(".!? ").split()
        if len(words) >= 3:
            cut_pos = random.randint(len(words) // 2, len(words) - 1)
            return " ".join(words[:cut_pos]) + "..."
        return text

    # 복문: 마지막 문장을 중간에서 자름
    last = sentences[-1].rstrip(".!? ")
    words = last.split()
    if len(words) >= 2:
        cut_pos = random.randint(1, max(1, len(words) - 1))
        sentences[-1] = " ".join(words[:cut_pos]) + "..."
        return join_sentences(sentences)

    return text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  통합 후처리 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def postprocess(
    text: str,
    glitch_level: int = 1,
    seed: Optional[int] = None,
) -> str:
    """LLM output을 품질 검증 → 글리치 후처리 파이프라인으로 처리한다.

    LoRA는 깨끗한 5세 아이 발화를 생성하고,
    이 함수가 글리치 효과를 사후 적용한다.
    → LoRA와 rule-base의 역할이 겹치지 않도록 분리.

    Args:
        text: 원본 LLM 출력 (LoRA가 생성한 깨끗한 5세 아이 발화)
        glitch_level: 글리치 단계 (1 / 2 / 3)
            1 — 정상 아이 (품질 검증만)
            2 — 혼란 (말 끊김, 에코, 자기 지칭 혼란)
            3 — 인형화 (감정 플랫화, 문장 단절, 전체 기법)
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    if seed is not None:
        random.seed(seed)

    # 1단계: 품질 검증/보정
    result, _issues = quality_gate(text)

    # 2단계: 글리치 후처리
    glitch_level = max(1, min(3, glitch_level))
    config = GLITCH_CONFIG[glitch_level]

    # 적용 순서:
    #   문장 단절(기저 텍스트 잘라냄) → 말 끊김(... 삽입)
    #   → 에코(키워드 반복) → 자기 지칭(나→인형)
    #   → 감정 플랫화(!?→.) → 호칭 반복(누나...)
    pipeline = [
        ("sentence_cut",     sentence_cut),
        ("stutter_pause",    stutter_pause),
        ("word_echo",        word_echo),
        ("self_confusion",   self_confusion),
        ("flatten_emotion",  flatten_emotion),
        ("calling_repeat",   calling_repeat),
    ]

    for name, fn in pipeline:
        prob = config.get(name, 0.0)
        if prob > 0 and random.random() < prob:
            result = fn(result)

    return result


def postprocess_batch(
    texts: List[str],
    glitch_level: int = 1,
    seed: Optional[int] = None,
) -> List[str]:
    """여러 출력을 한꺼번에 후처리한다.

    Args:
        texts: 원본 문자열 리스트
        glitch_level: 글리치 단계 (1 / 2 / 3)
        seed: 랜덤 시드

    Returns:
        후처리된 문자열 리스트
    """
    if seed is not None:
        random.seed(seed)

    return [postprocess(t, glitch_level=glitch_level) for t in texts]
