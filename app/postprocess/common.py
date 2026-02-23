"""후처리 공통 유틸리티"""

import re
from typing import List, Tuple


def split_sentences(text: str) -> List[str]:
    """텍스트를 문장 단위로 분리한다."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p.strip()]


def join_sentences(sentences: List[str]) -> str:
    """문장 리스트를 하나의 텍스트로 합친다."""
    return " ".join(s.strip() for s in sentences if s.strip())


def truncate_at_sentence(text: str, max_chars: int = 80) -> str:
    """max_chars 이내에서 마지막 문장 종결 부호 위치에서 자른다."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_end = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
    if last_end > 5:
        return truncated[:last_end + 1]
    return truncated.rstrip() + "."


def ensure_sentence_ending(text: str) -> str:
    """문장이 종결 부호 없이 끝나면 마침표를 붙인다."""
    stripped = text.rstrip()
    if stripped and stripped[-1] not in '.!?':
        return stripped + "."
    return stripped


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  세그먼트 인식 유틸리티 (대사 vs 서술 분리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def split_event_section(text: str) -> Tuple[str, str]:
    """텍스트에서 '사건:' 섹션을 분리한다.

    Returns:
        (main_text, event_text) — event_text 없으면 빈 문자열
    """
    match = re.search(r'\n사건:\s*', text)
    if match:
        return text[:match.start()].rstrip(), text[match.end():]
    # 줄바꿈 없이 텍스트 앞에 붙은 경우
    if text.startswith('사건:'):
        return '', text[len('사건:'):].lstrip()
    return text, ''


def parse_text_segments(text: str) -> List[Tuple[str, str]]:
    """텍스트를 대사(dialogue)·서술(description) 세그먼트 리스트로 분리한다.

    따옴표(") 안 = 'dialogue', 따옴표 밖 = 'description'.
    따옴표가 없는 순수 대사 텍스트는 [('dialogue', text)] 반환.
    닫히지 않은 마지막 따옴표는 끝까지를 dialogue로 간주한다.

    Returns:
        list of (type, content) — type은 'dialogue' 또는 'description'
    """
    if '"' not in text:
        return [('dialogue', text)]

    segments: List[Tuple[str, str]] = []
    pos = 0
    in_quote = False

    for m in re.finditer(r'"', text):
        quote_pos = m.start()
        chunk = text[pos:quote_pos]
        if chunk:
            seg_type = 'dialogue' if in_quote else 'description'
            segments.append((seg_type, chunk))
        in_quote = not in_quote
        pos = quote_pos + 1

    # 마지막 남은 텍스트
    remainder = text[pos:]
    if remainder:
        seg_type = 'dialogue' if in_quote else 'description'
        segments.append((seg_type, remainder))

    return segments


def normalize_description(text: str) -> str:
    """서술 파트에서 광기 후처리 아티팩트를 제거하여 자연스러운 서술로 정규화한다.

    제거 대상:
    - 에코 반복: '말했다?! 말했다?!!' → '말했다.'
    - 광기 부호: '?!' / '?!!' → '.', '!!+' → '!'
    - 과도한 말줄임표: '.....' → '...'
    """
    if not text.strip():
        return text

    # 에코 반복 제거: 동일 어절이 ?! 와 함께 반복
    # e.g. "말했다?! 말했다?!!" → "말했다."
    text = re.sub(r'(\S+)\?!+\s+\1\?!*', r'\1.', text)

    # 광기 부호 정규화: ?! 조합 → 마침표
    text = re.sub(r'\?!+', '.', text)

    # 연속 느낌표 2개 이상 → 느낌표 하나
    text = re.sub(r'!{2,}', '!', text)

    # 과도한 말줄임표 → 최대 3개
    text = re.sub(r'\.{4,}', '...', text)

    return text
