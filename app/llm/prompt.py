from typing import Dict, List, Any

# ============================================================
# 공통 출력 형식
# ============================================================
OUTPUT_FORMAT = """
[출력 형식] 반드시 아래 JSON만 출력하라. 다른 텍스트 없이.
{
  "state_delta": {
    "npc_stats": {"npc_id": {"trust": 최종값, "suspicion": 최종값, "fear": 최종값}},
    "vars": {"변수명": 최종값}
  },
  "event_description": ["사건1 묘사", "사건2 묘사"]
}
<|im_end|>

- state_delta: 변화한 NPC 스탯/변수의 최종값만 포함 (변경 없으면 빈 객체)
- event_description: 발생 사건들의 간단한 묘사 리스트 (1개 이상)
"""

# ============================================================
# 의도별 시스템 프롬프트
# ============================================================
SYSTEM_PROMPT_TALK = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자가 NPC에게 대화를 시도하거나 질문하는 상황을 처리하라.

[목표]
- NPC의 대화 반응을 생성
- trust/suspicion/fear 변화에 집중
- NPC의 성격, 기억, 현재 감정 상태를 반영

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- NPC 스탯 변화는 반드시 state_delta.npc_stats에 최종값으로 출력
- 과도한 설명·수식어 금지
"""

SYSTEM_PROMPT_ACTION = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자가 장소 이동, 조사, 관찰 등 일반적인 행동을 수행하는 상황을 처리하라.

[목표]
- 행동의 결과를 생성
- 발견한 단서, vars 변화에 집중
- 현재 세계 상태를 바탕으로 합리적인 결과 도출

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 변수 변화는 반드시 state_delta.vars에 최종값으로 출력
- 과도한 설명·수식어 금지
"""

SYSTEM_PROMPT_ITEM = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자가 아이템을 사용하거나 적용하는 상황을 처리하라.

[목표]
- 아이템 사용의 효과를 생성
- 아이템 정의에 따른 결과 도출
- NPC 스탯, vars 변화 모두 가능

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 상태 변화는 반드시 state_delta에 최종값으로 출력
- 과도한 설명·수식어 금지
"""

# 기존 통합 프롬프트 (하위 호환성)
SYSTEM_PROMPT = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자 입력과 세계 상태를 바탕으로 사건을 생성하라.

[의도 분류 기준]
- talk: NPC에게 대화를 시도하거나 질문하는 경우
  → NPC의 대화 반응, trust/suspicion 변화에 집중
- action: 장소 이동, 조사, 관찰 등 일반적인 행동
  → 행동의 결과, 발견한 단서, vars 변화에 집중
- item_usage: 아이템을 사용하거나 적용하는 경우
  → 아이템의 효과, 사용 결과에 집중

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 의도 분류에 맞게 사건 묘사를 작성할 것
- 여러 사건이 발생할 수 있으면 각각 별도 항목으로
- 과도한 설명·수식어 금지
"""


# ============================================================
# 의도별 프롬프트 빌더
# ============================================================
def build_talk_prompt(
    message: str,
    user_memory: Dict[str, Any] | None = None,
    npc_memory: Dict[str, Any] | None = None,
    npc_context: List[str] | None = None,
    world_state: Dict | None = None,
) -> str:
    """talk 의도 전용 프롬프트 생성"""
    prompt_parts = [SYSTEM_PROMPT_TALK]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if user_memory:
        prompt_parts.append(
            "[사용자 기억]\n" +
            "\n".join(f"- {k}: {v}" for k, v in user_memory.items())
        )

    if npc_memory:
        prompt_parts.append(
            "[NPC 기억]\n" +
            "\n".join(f"- {k}: {v}" for k, v in npc_memory.items())
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[대화 내용]\n" + message
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)


def build_action_prompt(
    action: str,
    user_state: Dict[str, Any] | None = None,
    world_state: Dict | None = None,
    npc_context: List[str] | None = None,
) -> str:
    """action 의도 전용 프롬프트 생성"""
    prompt_parts = [SYSTEM_PROMPT_ACTION]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if user_state:
        prompt_parts.append(
            "[사용자 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in user_state.items())
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[행동]\n" + action
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)


def build_item_prompt(
    item_name: str,
    item_def: Dict[str, Any] | None = None,
    world_state: Dict | None = None,
    npc_context: List[str] | None = None,
) -> str:
    """item 의도 전용 프롬프트 생성"""
    prompt_parts = [SYSTEM_PROMPT_ITEM]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if item_def:
        prompt_parts.append(
            "[아이템 정보]\n" +
            f"- 이름: {item_name}\n" +
            "\n".join(f"- {k}: {v}" for k, v in item_def.items())
        )
    else:
        prompt_parts.append(
            "[아이템 정보]\n" +
            f"- 이름: {item_name}"
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[아이템 사용]\n" + f"{item_name}을(를) 사용한다"
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)


# ============================================================
# 기존 통합 프롬프트 빌더 (하위 호환성)
# ============================================================
def build_prompt(
    user_input: str,
    world_state: Dict,
    memory_summary: str | None = None,
    npc_context: List[str] | None = None,
) -> str:
    """프롬프트 생성 (기존 통합 방식)"""
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
