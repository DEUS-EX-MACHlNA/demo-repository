"""
새엄마 캐릭터 대사 후처리 모듈

파이프라인: LLM 출력 → [품질 검증/보정] → [광기 후처리] → 최종 출력

1단계 - 품질 검증/보정 (Quality Gate)
   - 문장 완성도 검증 (미완성 문장 수정)
   - 캐릭터 이탈 감지 (독립 응원 등 통제적 성격 이탈)
   - 출력 길이 정규화

2단계 - 광기 후처리 (Madness Post-Processing)
   monstrosity 단계:
     1 — 변형 없음 (품질 검증만)
     2 — 중간 광기 (부호 강화 항상 + 극적 멈춤·늘려쓰기·문장 축약 확률)
     3 — 완전 광기 (부호 강화 + 에코 반복 항상 + 문법 붕괴·반복 등 확률)

   기법:
     1. 극적 멈춤      — 단어 사이에 … 삽입
     2. 어절 에코      — 문장 끝 어절을 ?! 로 반복
     3. 문장 축약      — 긴 문장을 짧은 명령/절규로 압축
     4. 문법 붕괴      — 조사 뒤에서 문장을 끊어 불안정하게
     5. 문장 부호 과격화 — . → ! / ? → ?! / ! → !!!
     6. 늘려쓰기       — 감정 단어의 모음을 늘려 광기 표현
     7. 속삭임 삽입     — 괄호 속 독백을 삽입
     8. 키워드 반복     — 집착 키워드를 되뇌이듯 반복
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
# "잘 할 수 있을 거야", "혼자서도 할 수 있어" 등 독립을 응원하는 패턴
CHARACTER_BREAK_PATTERNS = [
    re.compile(r'네가\s*할\s*수\s*있는\s*일이\s*많'),
    re.compile(r'잘\s*할\s*수\s*있을\s*거야'),
    re.compile(r'혼자.*잘\s*할\s*수\s*있'),
    re.compile(r'엄마\s*없이도.*할\s*수\s*있'),
    re.compile(r'네\s*힘으로.*할\s*수\s*있'),
    re.compile(r'넌.*잘\s*해낼\s*수\s*있'),
]

# 캐릭터 이탈 시 대체 출력 풀
FALLBACK_OUTPUTS = [
    "엄마 말 들어. 네가 뭘 안다고.",
    "그런 말 하면 안 돼. 엄마가 다 알아서 해줄게.",
    "엄마 없이는 아무것도 못 하면서. 엄마 곁에 있어.",
    "그래, 그렇게 생각할 수도 있지. 하지만 결국은 엄마한테 돌아올 거야.",
    "네가 원하는 대로 해봐. 하지만 엄마 없이는 안 될 거야.",
    "지금은 그렇게 말하지만, 엄마가 없으면 넌 아무것도 못 해.",
]


def _is_character_break(text: str) -> bool:
    """통제적 새엄마 캐릭터에서 이탈한 출력인지 감지한다."""
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

    # LLM LoRA 잔재 단어 제거 (예: 문장 끝에 "대사" 등이 붙는 경우)
    _LORA_ARTIFACTS = re.compile(r'\s*(대사|발화|나레이션|대화)\s*$')
    result = _LORA_ARTIFACTS.sub('', result).strip()

    # 빈 출력
    if len(result) < 2:
        issues.append("empty")
        result = random.choice(FALLBACK_OUTPUTS)
        return result, issues

    # 길이 정규화 (너무 긴 출력 → 문장 단위로 자름)
    if len(result) > 120:
        result = truncate_at_sentence(result, max_chars=120)
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
#  2단계: 광기 후처리 키워드·패턴 사전
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OBSESSIVE_KEYWORDS = [
    "엄마", "안 돼", "절대", "내 거", "내 딸", "혼자",
]

ELONGATION_MAP = {
    "안 돼":   ["안 돼에", "안 돼에에", "안 돼에에에"],
    "하지 마": ["하지 마아", "하지 마아아"],
    "엄마":    ["엄마아", "엄마아아"],
    "들어":    ["들으으라고", "들으으으라고"],
    "못 해":   ["못 해에", "못 해에에"],
    "무서워":  ["무서워어", "무서워어어"],
    "싫어":    ["싫어어", "싫어어어"],
    "가지 마": ["가지 마아", "가지 마아아"],
}

WHISPERS = [
    "(엄마잖아...)",
    "(내 딸이야...)",
    "(도망치면 안 돼...)",
    "(엄마 없이는...)",
    "(혼자 두지 마...)",
    "(다 알고 있어...)",
    "(엄마 말 들어...)",
    "(절대 보내지 않아...)",
    "(엄마만 있으면 돼...)",
]

SHORTEN_RULES = [
    ("안 돼",   ["안 돼!!!", "안 된다고!!!", "안 돼에에!!!"]),
    ("하지 마", ["하지 마!!!", "하지 말라고!!!"]),
    ("못",      ["못 해!!!", "못 한다고!!!"]),
    ("가지 마", ["가지 마!!!", "가지 말라고!!!"]),
    ("싫",      ["싫다고!!!", "싫어!!!"]),
    ("무서",    ["무섭다고!!!", "무서워!!!"]),
    ("들어",    ["들으라고!!!", "말 들어!!!"]),
]

CONTEXT_SHORTEN_RULES = [
    (["어디"],       ["가", "갈", "간"],   ["어디를 가!!!", "어디 가!!!"]),
    (["뭐", "무엇"], ["하", "할", "한"],   ["뭘 해!!!", "뭘 하려고!!!"]),
    (["누구"],       ["만나", "봐", "와"], ["누굴 만나!!!", "누구야!!!"]),
]

MONSTROSITY_CONFIG = {
    1: {
        "dramatic_pause":       0.00,
        "echo_phrase":          0.00,
        "intensify_punctuation": 0.00,
        "collapse_grammar":     0.00,
        "elongate_word":        0.00,
        "insert_whisper":       0.00,
        "repeat_keyword":       0.00,
        "shorten_sentence":     0.00,
    },
    2: {
        "dramatic_pause":       0.15,
        "echo_phrase":          0.00,
        "intensify_punctuation": 0.00,  # lv2는 mild_intensify_punctuation(필수)로만 처리 — 연속 부호 금지
        "collapse_grammar":     0.10,
        "elongate_word":        0.15,
        "insert_whisper":       0.00,
        "repeat_keyword":       0.00,
        "shorten_sentence":     0.10,
    },
    3: {
        "dramatic_pause":        0.30,
        "echo_phrase":           0.00,  # _GUARANTEED_TRANSFORMS에서 이미 적용
        "intensify_punctuation": 0.00,  # _GUARANTEED_TRANSFORMS에서 이미 적용
        "collapse_grammar":      0.20,  # fragment 생성 억제를 위해 감소
        "elongate_word":         0.40,
        "insert_whisper":        0.00,
        "repeat_keyword":        0.50,
        "shorten_sentence":      0.40,
        "stammer_repeat":        0.70,  # 신규: 주어 말더듬 효과
        "trailing_ellipsis":     0.60,  # 신규: 중간 문장 흐려짐
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  개별 변환 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def dramatic_pause(text: str) -> str:
    """단어 사이에 ...을 삽입하여 극적 멈춤/소름 효과

    '네가 어디 갈 생각을 해봤어?' → '네가... 어디 갈 생각을 해봤어?'
    """
    words = text.split()
    if len(words) < 3:
        return text

    insert_pos = random.randint(0, min(1, len(words) - 2))
    word = words[insert_pos].rstrip(".,!?")
    words[insert_pos] = word + "..."

    return " ".join(words)


def echo_phrase(text: str) -> str:
    """문장 끝 어절을 공격적으로 반복 (?!)

    '생각을 해봤어?'  → '생각을 해봤어?! 해봤어?!'
    """
    sentences = split_sentences(text)
    if not sentences:
        return text

    target_idx = 0 if len(sentences) <= 2 else random.randint(0, len(sentences) - 1)
    sentence = sentences[target_idx]

    clean = sentence.rstrip(".!? ")
    words = clean.split()
    if len(words) < 2:
        return text

    echo_len = random.choice([1, 2]) if len(words) >= 3 else 1
    echo_part = " ".join(words[-echo_len:])

    repeat_count = random.randint(1, 2)
    echo_suffix = " ".join([echo_part + "?!" for _ in range(repeat_count)])

    sentences[target_idx] = clean + "?! " + echo_suffix

    return join_sentences(sentences)


def shorten_sentence(text: str) -> str:
    """마지막 문장을 짧은 명령/절규로 압축"""
    sentences = split_sentences(text)
    if len(sentences) < 2:
        return text

    last = sentences[-1]
    preceding = " ".join(sentences[:-1])

    for prev_keys, cur_keys, replacements in CONTEXT_SHORTEN_RULES:
        has_prev = any(k in preceding for k in prev_keys)
        has_cur = any(k in last for k in cur_keys)
        if has_prev and has_cur:
            sentences[-1] = random.choice(replacements)
            return join_sentences(sentences)

    for keyword, replacements in SHORTEN_RULES:
        if keyword in last:
            sentences[-1] = random.choice(replacements)
            return join_sentences(sentences)

    words = last.rstrip(".!? ").split()
    if len(words) >= 3:
        core = " ".join(words[-2:])
        sentences[-1] = core + "!!!"
        return join_sentences(sentences)

    return text


def collapse_grammar(text: str) -> str:
    """조사 뒤에서 문장을 끊어 정신이 흔들리는 느낌

    '네가 가지면 안 돼.' → '네가. 가지면. 안 돼.'
    """
    if len(text) < 8:
        return text

    particles = r'(은|는|이|가|을|를|에서|에|도|만|으로|로|의|와|과|면|지)'
    count = random.randint(1, 2)
    return re.sub(particles + r'\s', r'\1. ', text, count=count)


def intensify_punctuation(text: str) -> str:
    """문장 부호를 과격하게 강화

    '.' → '!'  /  '?' → '?!'  /  '!' → '!!!'
    """
    sentences = split_sentences(text)
    if not sentences:
        return text

    result = []
    for sent in sentences:
        stripped = sent.rstrip(".!? ")
        ending = sent[len(stripped):]

        if "?" in ending:
            new_ending = random.choice(["?!", "?!!", "?!"])
        elif "!" in ending:
            new_ending = random.choice(["!!", "!", "!!"])
        else:
            new_ending = random.choice(["!", "!!", "!"])

        result.append(stripped + new_ending)

    return join_sentences(result)


def mild_intensify_punctuation(text: str) -> str:
    """lv2용 부드러운 부호 강화 — 마침표만 느낌표 하나로, 연속 부호 없음

    '엄마 곁에 있어야 해.' → '엄마 곁에 있어야 해!'
    ('?' / '!' 는 그대로 유지)
    """
    sentences = split_sentences(text)
    if not sentences:
        return text

    result = []
    for sent in sentences:
        stripped = sent.rstrip(".!? ")
        ending = sent[len(stripped):]

        if "?" in ending:
            new_ending = "?"   # 의문부호 유지
        elif "!" in ending:
            new_ending = "!"   # 이미 느낌표 — 유지
        else:
            new_ending = "!"   # 마침표 → 느낌표 하나

        result.append(stripped + new_ending)

    return join_sentences(result)


def elongate_word(text: str) -> str:
    """감정 단어의 모음을 늘려서 광기 표현

    '안 돼' → '안 돼에에'
    """
    for original, forms in ELONGATION_MAP.items():
        if original in text:
            text = text.replace(original, random.choice(forms), 1)
            break
    return text


def insert_whisper(text: str) -> str:
    """속삭임(내면 독백)을 문장 사이에 삽입

    '안 돼. 엄마 말대로 해.' → '안 돼. (엄마잖아...) 엄마 말대로 해.'
    """
    whisper = random.choice(WHISPERS)
    parts = split_sentences(text)

    if len(parts) >= 2:
        insert_pos = random.randint(1, len(parts) - 1)
        parts.insert(insert_pos, whisper)
        return join_sentences(parts)
    else:
        return text.rstrip() + " " + whisper


def repeat_keyword(text: str) -> str:
    """집착 키워드를 쉼표 반복으로 인라인 강조

    '엄마가 여기 있어!' → '엄마, 엄마가 여기 있어!'
    """
    for keyword in OBSESSIVE_KEYWORDS:
        if keyword not in text:
            continue
        text = text.replace(keyword, f"{keyword}, {keyword}", 1)
        break
    return text


_STAMMER_SUBJECTS = ["내가", "네가", "나는", "나한테"]


def stammer_repeat(text: str) -> str:
    """주어를 말더듬 스타일로 인라인 반복

    '내가 널 지켜줄게!!' → '내가, 내가! 널 지켜줄게!!'
    """
    sentences = split_sentences(text)
    for i, sent in enumerate(sentences):
        for subject in _STAMMER_SUBJECTS:
            idx = sent.find(subject)
            if idx == -1:
                continue
            before = sent[:idx]
            after = sent[idx + len(subject):]
            sentences[i] = before + subject + ", " + subject + "!" + after
            return join_sentences(sentences)
    return text


def trailing_ellipsis(text: str) -> str:
    """중간 문장 하나를 ...으로 끝내 광기적 흐려짐 효과

    '나한테 의지해야 해!' → '나한테 의지해야 해...'
    """
    sentences = split_sentences(text)
    if len(sentences) < 2:
        return text
    target_idx = random.randint(0, len(sentences) - 2)  # 마지막 문장 제외
    sent = sentences[target_idx]
    sentences[target_idx] = sent.rstrip(".!? ") + "..."
    return join_sentences(sentences)


# 필수 기법: lv2/3에서 항상 적용 (확률 파이프라인과 독립)
# lv2: mild_intensify_punctuation — 마침표→! 하나만 (연속 부호 없음, 절제된 광기 시작)
# lv3: intensify_punctuation + echo_phrase — 연속 부호 + 절규 반복으로 완전 광기 보장
_GUARANTEED_TRANSFORMS: dict[int, list] = {
    2: [mild_intensify_punctuation],
    3: [intensify_punctuation, echo_phrase],
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  통합 후처리 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def postprocess(
    text: str,
    monstrosity: int = 1,
    seed: Optional[int] = None,
) -> str:
    """LLM output을 품질 검증 → 광기 후처리 파이프라인으로 처리한다.

    Args:
        text: 원본 LLM 출력
        monstrosity: 광기 단계 (1 / 2 / 3)
            1 — 변형 없음 (품질 검증만)
            2 — 중간 광기 (극적 멈춤, 부호 강화 등)
            3 — 완전 광기 (에코, 문법 붕괴, 반복 등)
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    if seed is not None:
        random.seed(seed)

    # 1단계: 품질 검증/보정
    result, _issues = quality_gate(text)

    monstrosity = max(1, min(3, monstrosity))

    # 2단계: 필수 기법 (lv2+: 항상 적용, 변형 보장)
    for fn in _GUARANTEED_TRANSFORMS.get(monstrosity, []):
        result = fn(result)

    # 3단계: 확률 기법
    config = MONSTROSITY_CONFIG[monstrosity]

    pipeline = [
        ("shorten_sentence",      shorten_sentence),
        ("dramatic_pause",        dramatic_pause),
        ("echo_phrase",           echo_phrase),
        ("collapse_grammar",      collapse_grammar),
        ("elongate_word",         elongate_word),
        ("intensify_punctuation", intensify_punctuation),
        ("insert_whisper",        insert_whisper),
        ("repeat_keyword",        repeat_keyword),
        ("stammer_repeat",        stammer_repeat),
        ("trailing_ellipsis",     trailing_ellipsis),
    ]

    for name, fn in pipeline:
        prob = config.get(name, 0.0)
        if prob > 0 and random.random() < prob:
            result = fn(result)

    return result


def postprocess_batch(
    texts: List[str],
    monstrosity: int = 1,
    seed: Optional[int] = None,
) -> List[str]:
    """여러 출력을 한꺼번에 후처리한다.

    Args:
        texts: 원본 문자열 리스트
        monstrosity: 광기 단계 (1 / 2 / 3)
        seed: 랜덤 시드

    Returns:
        후처리된 문자열 리스트
    """
    if seed is not None:
        random.seed(seed)

    return [postprocess(t, monstrosity=monstrosity) for t in texts]
