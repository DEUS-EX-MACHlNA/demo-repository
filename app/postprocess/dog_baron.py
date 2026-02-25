"""강아지(바론) 행동 묘사 후처리 모듈

LoRA / rule-base 역할 분리:
  - LoRA가 학습하는 것: 3인칭 행동 묘사 문체, 개의 행동 어휘, 감정별 반응
  - rule-base가 처리하는 것: 호감도 레벨에 따른 행동 모디파이어 삽입

파이프라인: LLM 출력 → [품질 검증/보정] → [행동 모디파이어 후처리] → 최종 출력

1단계 - 품질 검증/보정 (Quality Gate)
   - 빈 출력 감지 → 대체 출력 (행동 묘사 형식)
   - 출력 길이 정규화 (80자)
   - 1인칭 발화 감지 (개는 말을 하지 않음)
   - 문장 완성도 검증

2단계 - 행동 모디파이어 후처리 (Action Modifier Post-Processing)
   loyalty_level:
     1 — 우호적 (우호 행동 항상 + 묘사체 종결 확률)
     2 — 중립/경계 (경계 행동 항상 + 묘사체 종결 확률)
     3 — 적대적 (적대 행동 항상 + 묘사체 종결 확률)

   기법:
     1. 우호 모디파이어  — 꼬리 흔들기 / 낑낑거림 접두 삽입 (레벨 1)
     2. 경계 모디파이어  — 코 킁킁 / 귀 쫑긋 접두 삽입 (레벨 2)
     3. 적대 모디파이어  — 으르렁 / 짖기 접두 삽입 (레벨 3)
     4. 묘사체 종결 보정 — 행동 묘사 종결형(~합니다) 정규화
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
# 행동 묘사가 아닌 직접 발화 (개는 말을 하지 않음)
CHARACTER_BREAK_PATTERNS = [
    re.compile(r'^"'),                # 큰따옴표 대사
    re.compile(r'^\''),               # 작은따옴표 대사
    re.compile(r'나는\s'),            # 1인칭 발화
    re.compile(r'저는\s'),            # 1인칭 발화
    re.compile(r'제가\s'),            # 1인칭 발화
    re.compile(r'바론이?\s*말한'),    # "바론이 말한다" 류
    re.compile(r'바론이?\s*대답'),    # "바론이 대답한다" 류
]

# 캐릭터 이탈 시 대체 출력 풀 (행동 묘사 형식)
FALLBACK_OUTPUTS = [
    "바론이 가만히 앉아서 바라봅니다.",
    "바론이 코를 킁킁거리며 주위를 살핍니다.",
    "바론이 고개를 갸웃거리며 당신을 바라봅니다.",
    "바론이 느릿느릿 꼬리를 흔듭니다.",
    "바론이 낮게 낑낑거리며 당신 쪽으로 다가옵니다.",
]


def _is_character_break(text: str) -> bool:
    """행동 묘사 형식에서 이탈한 출력인지 감지한다."""
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

    # 길이 정규화 (행동 묘사 — 80자 기준)
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
#  2단계: 행동 모디파이어 사전
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 우호적 행동 모디파이어
FRIENDLY_MODIFIERS = [
    "꼬리를 세차게 흔들며 ",
    "꼬리를 흔들며 ",
    "기쁜 듯 낑낑거리며 ",
    "앞발을 살짝 들며 ",
    "당신의 손을 핥으려 하며 ",
]

# 경계/중립 행동 모디파이어
CAUTIOUS_MODIFIERS = [
    "코를 킁킁거리며 ",
    "고개를 갸웃거리며 ",
    "천천히 다가서며 ",
    "귀를 쫑긋 세우며 ",
    "조심스럽게 냄새를 맡으며 ",
]

# 적대적 행동 모디파이어
HOSTILE_MODIFIERS = [
    "낮게 으르렁거리며 ",
    "날카롭게 짖으며 ",
    "이빨을 드러내며 ",
    "뒷걸음치며 ",
    "등털을 세우며 ",
]

# 주체 패턴 ("바론이" / "바론은" 뒤에 모디파이어 삽입)
_SUBJECT_PATTERNS = [
    ("바론이 ", "바론이 "),
    ("바론은 ", "바론은 "),
]

# 충성도 레벨별 확률 설정
LOYALTY_CONFIG = {
    1: {  # 우호적
        "friendly_modifier":   0.70,
        "cautious_modifier":   0.00,
        "hostile_modifier":    0.00,
        "narrative_ending_fix": 0.20,
    },
    2: {  # 중립/경계
        "friendly_modifier":   0.10,
        "cautious_modifier":   0.50,
        "hostile_modifier":    0.10,
        "narrative_ending_fix": 0.20,
    },
    3: {  # 적대적
        "friendly_modifier":   0.00,
        "cautious_modifier":   0.10,
        "hostile_modifier":    0.70,
        "narrative_ending_fix": 0.20,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  개별 변환 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _insert_modifier(text: str, modifier: str) -> str:
    """'바론이 ' / '바론은 ' 뒤에 모디파이어를 삽입한다."""
    for original, _ in _SUBJECT_PATTERNS:
        if original in text:
            return text.replace(original, original + modifier, 1)
    # 폴백: 텍스트 앞에 붙임
    return modifier + text


def friendly_modifier(text: str) -> str:
    """우호적 행동 모디파이어를 삽입

    '바론이 당신 앞에 앉습니다.' → '바론이 꼬리를 흔들며 당신 앞에 앉습니다.'
    """
    return _insert_modifier(text, random.choice(FRIENDLY_MODIFIERS))


def cautious_modifier(text: str) -> str:
    """경계/중립 행동 모디파이어를 삽입

    '바론이 멈춥니다.' → '바론이 코를 킁킁거리며 멈춥니다.'
    """
    return _insert_modifier(text, random.choice(CAUTIOUS_MODIFIERS))


def hostile_modifier(text: str) -> str:
    """적대적 행동 모디파이어를 삽입

    '바론이 물러섭니다.' → '바론이 낮게 으르렁거리며 물러섭니다.'
    """
    return _insert_modifier(text, random.choice(HOSTILE_MODIFIERS))


def narrative_ending_fix(text: str) -> str:
    """행동 묘사 문체의 종결 표현을 '~합니다' 형태로 정규화

    '바론이 달려와.' → '바론이 달려옵니다.'
    (이미 묘사체이면 통과)
    """
    narrative_endings = ("합니다.", "입니다.", "습니다.", "ㅂ니다.")
    stripped = text.rstrip()
    if any(stripped.endswith(e) for e in narrative_endings):
        return text  # 이미 묘사체 종결

    # 구어체 종결 → 묘사체로 보정
    conversational_map = [
        ("와.", "옵니다."),
        ("가.", "갑니다."),
        ("봐.", "봅니다."),
        ("해.", "합니다."),
        ("서.", "섭니다."),
        ("어.", "습니다."),
        ("아.", "습니다."),
    ]
    for old, new in conversational_map:
        if stripped.endswith(old):
            return stripped[:-len(old)] + new

    return stripped + "습니다."


# 필수 기법: 모든 레벨에서 항상 적용 (확률 파이프라인과 독립)
# 각 레벨이 서로 다른 행동 모드를 표현하므로 1/2/3 모두 보장
# lv1: friendly_modifier — 우호 행동 항상 (꼬리 흔들기 등)
# lv2: cautious_modifier — 경계 행동 항상 (코 킁킁 등)
# lv3: hostile_modifier  — 적대 행동 항상 (으르렁 등)
_GUARANTEED_TRANSFORMS: dict[int, list] = {
    1: [friendly_modifier],
    2: [cautious_modifier],
    3: [hostile_modifier],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  통합 후처리 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def postprocess(
    text: str,
    loyalty_level: int = 1,
    seed: Optional[int] = None,
) -> str:
    """LLM output을 품질 검증 → 행동 모디파이어 파이프라인으로 처리한다.

    LoRA는 깨끗한 행동 묘사 문장을 생성하고,
    이 함수가 호감도에 따른 행동 모디파이어를 사후 적용한다.

    Args:
        text: 원본 LLM 출력 (3인칭 행동 묘사 형식)
        loyalty_level: 충성도 레벨 (1 / 2 / 3)
            1 — 우호적 (꼬리 흔들기, 아이템 유인)
            2 — 중립/경계 (관찰, 냄새 맡기)
            3 — 적대적 (짖기, 으르렁, 거리 두기)
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    if seed is not None:
        random.seed(seed)

    # 1단계: 품질 검증/보정
    result, _issues = quality_gate(text)

    loyalty_level = max(1, min(3, loyalty_level))

    # 2단계: 필수 기법 (모든 레벨에서 항상 적용, 변형 보장)
    for fn in _GUARANTEED_TRANSFORMS.get(loyalty_level, []):
        result = fn(result)

    # 3단계: 확률 기법
    config = LOYALTY_CONFIG[loyalty_level]

    # 적용 순서: 모디파이어(접두 행동) → 묘사체 종결 보정
    pipeline = [
        ("friendly_modifier",    friendly_modifier),
        ("cautious_modifier",    cautious_modifier),
        ("hostile_modifier",     hostile_modifier),
        ("narrative_ending_fix", narrative_ending_fix),
    ]

    for name, fn in pipeline:
        prob = config.get(name, 0.0)
        if prob > 0 and random.random() < prob:
            result = fn(result)

    return result


def postprocess_batch(
    texts: List[str],
    loyalty_level: int = 1,
    seed: Optional[int] = None,
) -> List[str]:
    """여러 출력을 한꺼번에 후처리한다.

    Args:
        texts: 원본 문자열 리스트
        loyalty_level: 충성도 레벨 (1 / 2 / 3)
        seed: 랜덤 시드

    Returns:
        후처리된 문자열 리스트
    """
    if seed is not None:
        random.seed(seed)

    return [postprocess(t, loyalty_level=loyalty_level) for t in texts]
