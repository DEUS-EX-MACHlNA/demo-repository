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


def format_emotion(stats: dict[str, int]) -> str:
    """감정 상태를 프롬프트용 문자열로 포맷.

    Args:
        stats: NPC 스탯 Dict (예: {"affection": 50, "fear": 80, "humanity": 0})
    """
    if not stats:
        return "(스탯 정보 없음)"
    return ", ".join(f"{k}={v}" for k, v in stats.items())


def extract_number(text: str, default: float = 5.0) -> float:
    """텍스트에서 첫 번째 숫자를 추출. 실패 시 default 반환."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    return default


def clamp(value: int, lo: int = -2, hi: int = 2) -> int:
    return max(lo, min(hi, value))


def parse_stat_changes_text(text: str, stat_names: list[str] | None = None) -> dict[str, int]:
    """LLM 응답에서 스탯 변화량 파싱.

    Args:
        text: LLM 응답 텍스트
        stat_names: 파싱할 스탯 이름 리스트 (예: ["affection", "fear", "humanity"])
                    None이면 텍스트에서 "이름: 숫자" 패턴을 자동 감지

    예상 포맷: "affection: +1, fear: 0, humanity: -1"
    """
    result: dict[str, int] = {}
    if stat_names:
        for stat in stat_names:
            m = re.search(rf"{stat}\s*[:=]\s*([+-]?\d+)", text, re.IGNORECASE)
            if m:
                result[stat] = clamp(int(m.group(1)))
    else:
        # 자동 감지: "word: number" 패턴
        for m in re.finditer(r"(\w+)\s*[:=]\s*([+-]?\d+)", text):
            stat_name = m.group(1).lower()
            result[stat_name] = clamp(int(m.group(2)))
    return result
