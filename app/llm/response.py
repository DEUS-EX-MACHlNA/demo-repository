from dataclasses import dataclass

@dataclass
class LLM_Response:
    raw_text: str
    cleaned_text: str
    confidence: float | None = None


def clean_text(text: str) -> str:
    return text.strip()


def parse_response(raw_text: str) -> LLM_Response:
    cleaned = clean_text(raw_text)

    # 나중에 JSON, DSL, 태그 기반 파싱이 여기 들어감
    return LLM_Response(
        raw_text=raw_text,
        cleaned_text=cleaned,
        confidence=None
    )
