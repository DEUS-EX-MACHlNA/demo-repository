from typing import Dict, List

SYSTEM_PROMPT = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
세계관과 등장인물의 일관성을 유지하며, 과도한 설명을 피하고
현재 상황에서 자연스럽게 이어지는 서술만 생성하라.
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

    prompt_parts.append(
        "[출력]\n"
    )

    return "\n\n".join(prompt_parts)
