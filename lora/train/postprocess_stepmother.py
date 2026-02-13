"""
새엄마 캐릭터 대사 후처리 모듈

파이프라인: LLM 출력 → [품질 검증/보정] → [광기 후처리] → 최종 출력

1단계 - 품질 검증/보정 (Quality Gate)
   - 문장 완성도 검증 (미완성 문장 수정)
   - 캐릭터 이탈 감지 (독립 응원 등 통제적 성격 이탈)
   - 출력 길이 정규화

2단계 - 광기 후처리 (Madness Post-Processing)
   monstrosity 단계:
     1 — 변형 없음
     2 — 중간 광기 (극적 멈춤, 부호 강화, 늘려쓰기, 문장 축약)
     3 — 완전 광기 (에코, 문법 붕괴, 반복 등 모든 기법)

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


def _truncate_at_sentence(text: str, max_chars: int = 120) -> str:
    """max_chars 이내에서 마지막 문장 종결 부호 위치에서 자른다."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_end = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
    if last_end > 10:
        return truncated[:last_end + 1]
    return truncated.rstrip() + "."


def _ensure_sentence_ending(text: str) -> str:
    """문장이 종결 부호 없이 끝나면 마침표를 붙인다."""
    stripped = text.rstrip()
    if stripped and stripped[-1] not in '.!?':
        return stripped + "."
    return stripped


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

    # 빈 출력
    if len(result) < 2:
        issues.append("empty")
        result = random.choice(FALLBACK_OUTPUTS)
        return result, issues

    # 길이 정규화 (너무 긴 출력 → 문장 단위로 자름)
    if len(result) > 120:
        result = _truncate_at_sentence(result, max_chars=120)
        issues.append("truncated")

    # 문장 완성도 (종결 부호 확인)
    before = result
    result = _ensure_sentence_ending(result)
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
        "intensify_punctuation": 0.30,
        "collapse_grammar":     0.10,
        "elongate_word":        0.15,
        "insert_whisper":       0.00,
        "repeat_keyword":       0.00,
        "shorten_sentence":     0.10,
    },
    3: {
        "dramatic_pause":       0.30,
        "echo_phrase":          0.70,
        "intensify_punctuation": 0.90,
        "collapse_grammar":     0.50,
        "elongate_word":        0.50,
        "insert_whisper":       0.00,
        "repeat_keyword":       0.40,
        "shorten_sentence":     0.50,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _split_sentences(text: str) -> List[str]:
    """텍스트를 문장 단위로 분리한다."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p.strip()]


def _join_sentences(sentences: List[str]) -> str:
    """문장 리스트를 하나의 텍스트로 합친다."""
    return " ".join(s.strip() for s in sentences if s.strip())


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
    sentences = _split_sentences(text)
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

    return _join_sentences(sentences)


def shorten_sentence(text: str) -> str:
    """마지막 문장을 짧은 명령/절규로 압축"""
    sentences = _split_sentences(text)
    if len(sentences) < 2:
        return text

    last = sentences[-1]
    preceding = " ".join(sentences[:-1])

    for prev_keys, cur_keys, replacements in CONTEXT_SHORTEN_RULES:
        has_prev = any(k in preceding for k in prev_keys)
        has_cur = any(k in last for k in cur_keys)
        if has_prev and has_cur:
            sentences[-1] = random.choice(replacements)
            return _join_sentences(sentences)

    for keyword, replacements in SHORTEN_RULES:
        if keyword in last:
            sentences[-1] = random.choice(replacements)
            return _join_sentences(sentences)

    words = last.rstrip(".!? ").split()
    if len(words) >= 3:
        core = " ".join(words[-2:])
        sentences[-1] = core + "!!!"
        return _join_sentences(sentences)

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
    sentences = _split_sentences(text)
    if not sentences:
        return text

    result = []
    for sent in sentences:
        stripped = sent.rstrip(".!? ")
        ending = sent[len(stripped):]

        if "?" in ending:
            new_ending = random.choice(["?!", "?!!", "?!?!"])
        elif "!" in ending:
            new_ending = random.choice(["!!!", "!!", "!!!"])
        else:
            new_ending = random.choice(["!", "!!", "!"])

        result.append(stripped + new_ending)

    return _join_sentences(result)


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
    parts = _split_sentences(text)

    if len(parts) >= 2:
        insert_pos = random.randint(1, len(parts) - 1)
        parts.insert(insert_pos, whisper)
        return _join_sentences(parts)
    else:
        return text.rstrip() + " " + whisper


def repeat_keyword(text: str) -> str:
    """집착 키워드를 되뇌이듯 반복

    '엄마가 다 알아서 해.' → '엄마가 다 알아서 해. 엄마... 엄마...'
    """
    for keyword in OBSESSIVE_KEYWORDS:
        if keyword not in text:
            continue

        repeat_count = random.randint(2, 3)
        connector = random.choice([".", ".", "!", "..."])
        fragments = [keyword + connector for _ in range(repeat_count)]

        text = text.rstrip(".!? ") + ". " + " ".join(fragments)
        break

    return text


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

    # 2단계: 광기 후처리
    monstrosity = max(1, min(3, monstrosity))
    config = MONSTROSITY_CONFIG[monstrosity]

    pipeline = [
        ("shorten_sentence",     shorten_sentence),
        ("dramatic_pause",       dramatic_pause),
        ("echo_phrase",          echo_phrase),
        ("collapse_grammar",     collapse_grammar),
        ("elongate_word",        elongate_word),
        ("intensify_punctuation", intensify_punctuation),
        ("insert_whisper",       insert_whisper),
        ("repeat_keyword",       repeat_keyword),
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  데모
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    test_outputs = [
        "지하실은 엄마의 영역이야. 네가 가지면 안 돼.",
        "그래, 넌 엄마 없어도 잘할 수 있을 거야. 엄마 없이도 네가 할 수 있는 일이 많아.",
        "네가 어디 갈 생각을 해봤어? 네가 가고 싶어하는 곳이 있어도 엄마는 안 돼.",
        "그냥 엄마 말고 하면 안 돼. 엄마 말대로 해야 해.",
        "그래, 알았어. 지금은 엄마 옆에 앉아 있어. 그래, 엄마가 잘 지켜줄게.",
        "엄마가 없으면 넌 누구한테 기대고 싶어? 아무도 아니야. 엄마 밖에 없어. 그러니까 엄마 말 들어. 너는 아직 어리고 세상은 위험하니까 엄마가 항상 곁에 있어야 해.",
        "",
        "왜 그러니? 엄마 없이 할 수 있으면",
    ]

    print("=" * 70)
    print("  POSTPROCESS DEMO")
    print("=" * 70)

    # 품질 검증 데모
    print("\n--- 1단계: 품질 검증 ---")
    for i, text in enumerate(test_outputs):
        fixed, issues = quality_gate(text)
        if issues:
            print(f"\n  [{i}] BEFORE: {repr(text)}")
            print(f"       AFTER:  {fixed}")
            print(f"       ISSUES: {issues}")

    # 광기 후처리 데모
    print("\n--- 2단계: 통합 파이프라인 (품질 검증 + 광기) ---")
    clean_outputs = [t for t in test_outputs if len(t.strip()) > 5 and not _is_character_break(t)]
    for level in [1, 2, 3]:
        print(f"\n  monstrosity = {level}")
        for i, original in enumerate(clean_outputs[:5]):
            processed = postprocess(original, monstrosity=level, seed=i * 100 + level)
            if original.strip() != processed:
                print(f"    [{i}] BEFORE: {original}")
                print(f"         AFTER:  {processed}")
