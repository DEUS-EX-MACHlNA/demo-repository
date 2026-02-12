"""후처리 공통 유틸리티"""

import re
from typing import List


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
