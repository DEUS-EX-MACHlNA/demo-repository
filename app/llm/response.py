import json
import re

from typing import Dict, Any
from app.schemas.llm_parsed_response import LLMParsedResponse

import logging

logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    return text.strip()


def _extract_json(text: str) -> dict | None:
    """응답 텍스트에서 JSON 객체 추출"""
    text = text.strip()
    # ```json ... ``` 블록 확인
    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    # 중괄호로 시작하는 JSON 직접 탐색
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def parse_response(raw_text: str) -> LLMParsedResponse:
    cleaned = clean_text(raw_text)
    state_delta: dict = {}
    event_description: list[str] = []

    parsed = _extract_json(raw_text)
    if parsed:
        state_delta = parsed.get("state_delta", {})
        if not isinstance(state_delta, dict):
            state_delta = {}
        raw_events = parsed.get("event_description", [])
        if isinstance(raw_events, list):
            event_description = [str(e).strip() for e in raw_events if e]
        elif isinstance(raw_events, str):
            event_description = [raw_events.strip()] if raw_events.strip() else []

    # JSON 파싱 실패 시 cleaned_text를 단일 이벤트로
    if not event_description and cleaned:
        event_description = [cleaned]

    return LLMParsedResponse(
        raw_text=raw_text,
        cleaned_text=cleaned,
        state_delta=state_delta,
        event_description=event_description,
        confidence=None,
    )

def parse_tool_call_response(raw_output: str, fallback_input: str) -> Dict[str, Any]:
    """
    LLM의 tool call 응답을 파싱합니다.

    Args:
        raw_output: LLM 출력
        fallback_input: 파싱 실패 시 action으로 사용할 입력

    Returns:
        {"tool_name": str, "args": dict, "intent": str}
    """
    VALID_INTENTS = ("investigate", "obey", "rebel", "reveal", "summarize", "neutral")

    # JSON 블록 추출
    json_match = re.search(r'```json\s*(.*?)\s*```', raw_output, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # ```json 없이 JSON만 있는 경우
        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            logger.warning(f"[call_tool] JSON 파싱 실패, fallback to action: {raw_output[:100]}")
            return {
                "tool_name": "action",
                "args": {"action": fallback_input},
                "intent": "neutral",
            }

    try:
        data = json.loads(json_str)
        tool_name = data.get("tool_name", "action")
        args = data.get("args", {})
        intent = data.get("intent", "neutral")

        # tool 유효성 검사
        if tool_name not in ("interact", "action", "use"):
            logger.warning(f"[call_tool] 알 수 없는 tool: {tool_name}, fallback to action")
            return {
                "tool_name": "action",
                "args": {"action": fallback_input},
                "intent": "neutral",
            }

        # intent 유효성 검사
        if intent not in VALID_INTENTS:
            logger.warning(f"[call_tool] 알 수 없는 intent: {intent}, fallback to neutral")
            intent = "neutral"

        return {"tool_name": tool_name, "args": args, "intent": intent}

    except json.JSONDecodeError as e:
        logger.warning(f"[call_tool] JSON 디코드 실패: {e}, fallback to action")
        return {
            "tool_name": "action",
            "args": {"action": fallback_input},
            "intent": "neutral",
        }


def parse_narrative_response(raw_text: str) -> str:
    """내러티브 LLM 응답에서 서술 텍스트 추출 — [출력] 마커 이후 텍스트 반환"""
    text = clean_text(raw_text)
    marker = "[출력]"
    idx = text.rfind(marker)
    if idx >= 0:
        text = text[idx + len(marker):].strip()
    if not text:
        return "(서술 생성 실패)"
    return text
