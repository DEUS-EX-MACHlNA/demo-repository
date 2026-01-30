from typing import Dict, List

SYSTEM_PROMPT = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자 입력과 세계 상태를 바탕으로 발생할 수 있는 사건들을 예측하고,
간결한 묘사와 함께 JSON 형식으로 출력한다.

규칙:
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 여러 사건이 발생할 수 있으면 각각 별도 항목으로
- 과도한 설명·수식어 금지
"""

OUTPUT_FORMAT = """
[출력 형식] 반드시 아래 JSON만 출력하라. 다른 텍스트 없이.
{
  "state_delta": {
    "npc_stats": {"npc_id": {"trust": 최종값, "suspicion": 최종값}},
    "vars": {"변수명": 최종값}
  },
  "event_description": ["사건1 묘사", "사건2 묘사"]
}

- state_delta: 변화한 NPC 스탯/변수의 최종값만 포함 (변경 없으면 빈 객체)
- event_description: 발생 사건들의 간단한 묘사 리스트 (1개 이상)
"""


def build_prompt(
    user_input: str,
    world_state: Dict,
    memory_summary: str | None = None,
    npc_context: List[str] | None = None,
) -> str:
    prompt_parts = [SYSTEM_PROMPT]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if memory_summary:
        prompt_parts.append(
            "[이전 요약]\n" + memory_summary
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[사용자 입력]\n" + user_input
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)
