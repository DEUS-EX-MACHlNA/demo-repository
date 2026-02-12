"""NPC 대사 후처리 모듈

npc_id에 따라 적절한 후처리기를 선택하여 LLM 출력에 적용한다.
- brother (동생/루카스): 글리치 효과 (말 끊김, 에코, 자기 지칭 혼란 등)
- stepmother (새엄마/엘리노어): 광기 효과 (극적 멈춤, 부호 강화, 문법 붕괴 등)
- 그 외 NPC: 후처리 없이 원문 반환
"""

from __future__ import annotations

from typing import Optional

from .sibling import postprocess as sibling_postprocess
from .stepmother import postprocess as stepmother_postprocess


def humanity_to_level(humanity: int) -> int:
    """humanity 스탯(0~100)을 후처리 레벨(1~3)로 변환한다.

    - humanity >= 70 → 1 (정상)
    - 40 <= humanity < 70 → 2 (혼란 / 중간 광기)
    - humanity < 40 → 3 (인형화 / 완전 광기)
    """
    if humanity >= 70:
        return 1
    elif humanity >= 40:
        return 2
    else:
        return 3


def postprocess_npc_dialogue(
    text: str,
    npc_id: str,
    humanity: int = 100,
    seed: Optional[int] = None,
) -> str:
    """npc_id에 따라 적절한 후처리기를 선택하여 적용한다.

    Args:
        text: 원본 LLM 출력
        npc_id: NPC 식별자 ("brother", "stepmother" 등)
        humanity: NPC의 humanity 스탯 (0~100)
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    level = humanity_to_level(humanity)

    if npc_id == "brother":
        return sibling_postprocess(text, glitch_level=level, seed=seed)
    elif npc_id == "stepmother":
        return stepmother_postprocess(text, monstrosity=level, seed=seed)
    else:
        return text
