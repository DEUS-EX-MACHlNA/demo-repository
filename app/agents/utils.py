"""
app/agents/utils.py
Generative Agents 공유 유틸리티
"""
from __future__ import annotations

import re
from typing import Any


def format_persona(persona: dict[str, Any]) -> str:
    """NPC persona dict를 프롬프트용 한국어 문자열로 포맷."""
    values = ", ".join(persona.get("values", []))
    taboos = ", ".join(persona.get("taboos", []))
    parts = []
    if values:
        parts.append(f"가치관: {values}")
    if taboos:
        parts.append(f"금기: {taboos}")
    return "\n".join(parts) if parts else "(정보 없음)"


def format_emotion(trust: int, fear: int, suspicion: int) -> str:
    """감정 상태를 프롬프트용 문자열로 포맷."""
    return f"신뢰={trust}, 두려움={fear}, 의심={suspicion}"


def extract_number(text: str, default: float = 5.0) -> float:
    """텍스트에서 첫 번째 숫자를 추출. 실패 시 default 반환."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    return default


def clamp(value: int, lo: int = -2, hi: int = 2) -> int:
    return max(lo, min(hi, value))


def parse_stat_changes_text(text: str) -> dict[str, int]:
    """LLM 응답에서 trust/fear/suspicion 변화량 파싱.

    예상 포맷: "trust: +1, fear: 0, suspicion: -1"
    """
    result: dict[str, int] = {}
    for stat in ("trust", "fear", "suspicion"):
        m = re.search(rf"{stat}\s*[:=]\s*([+-]?\d+)", text, re.IGNORECASE)
        if m:
            result[stat] = clamp(int(m.group(1)))
    return result
