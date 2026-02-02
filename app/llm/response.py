import json
import re
from dataclasses import dataclass


@dataclass
class LLM_Response:
    raw_text: str
    cleaned_text: str
    state_delta: dict
    event_description: list[str]
    intention: str = "action"  # talk, action, item_usage
    confidence: float | None = None


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


def parse_response(raw_text: str) -> LLM_Response:
    cleaned = clean_text(raw_text)
    state_delta: dict = {}
    event_description: list[str] = []
    intention: str = "action"

    parsed = _extract_json(raw_text)
    if parsed:
        # intention 파싱
        raw_intention = parsed.get("intention", "action")
        if raw_intention in ["talk", "action", "item_usage"]:
            intention = raw_intention

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

    return LLM_Response(
        raw_text=raw_text,
        cleaned_text=cleaned,
        state_delta=state_delta,
        event_description=event_description,
        intention=intention,
        confidence=None,
    )
