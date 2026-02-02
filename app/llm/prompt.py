from typing import Dict, List

# ============================================================
# 통합 시스템 프롬프트 (intention 분류 + 결과 생성을 한 번에)
# ============================================================
SYSTEM_PROMPT = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자 입력과 세계 상태를 바탕으로:
1. 사용자의 의도(intention)를 분류하고
2. 해당 의도에 맞는 사건을 생성하라.

[의도 분류 기준]
- talk: NPC에게 대화를 시도하거나 질문하는 경우
  → NPC의 대화 반응, trust/suspicion 변화에 집중
- action: 장소 이동, 조사, 관찰 등 일반적인 행동
  → 행동의 결과, 발견한 단서, vars 변화에 집중
- item_usage: 아이템을 사용하거나 적용하는 경우
  → 아이템의 효과, 사용 결과에 집중

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 여러 사건이 발생할 수 있으면 각각 별도 항목으로
- 과도한 설명·수식어 금지
"""

OUTPUT_FORMAT = """
[출력 형식] 반드시 아래 JSON만 출력하라. 다른 텍스트 없이.
{
  "intention": "talk" | "action" | "item_usage",
  "state_delta": {
    "npc_stats": {"npc_id": {"trust": 최종값, "suspicion": 최종값}},
    "vars": {"변수명": 최종값}
  },
  "event_description": ["사건1 묘사", "사건2 묘사"]
}

- intention: 사용자 입력의 의도 (talk, action, item_usage 중 하나)
- state_delta: 변화한 NPC 스탯/변수의 최종값만 포함 (변경 없으면 빈 객체)
- event_description: 발생 사건들의 간단한 묘사 리스트 (1개 이상)
"""


def build_prompt(
    user_input: str,
    world_state: Dict,
    memory_summary: str | None = None,
    npc_context: List[str] | None = None,
) -> str:
    """통합 프롬프트 생성 (intention 분류 + 결과 생성을 한 번에)"""
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
