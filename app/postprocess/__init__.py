"""NPC 대사 후처리 모듈

npc_id에 따라 적절한 후처리기를 선택하여 LLM 출력에 적용한다.
- brother    (동생/루카스):  글리치 효과 (말 끊김, 에코, 자기 지칭 혼란 등)
- stepmother (새엄마/엘리노어): 광기 효과 (극적 멈춤, 부호 강화, 문법 붕괴 등)
- stepfather (새아빠/아더):  억압 효과 (기억 혼란, 명령 강화, 문장 압축 등)
- grandmother (할머니/마가렛): 의식 붕괴 효과 (숨 멈춤, 단어 부식, 문장 단절 등)
- dog_baron  (강아지/바론):  행동 모디파이어 (우호/경계/적대 행동 묘사 삽입)
- 그 외 NPC: 후처리 없이 원문 반환
"""

from __future__ import annotations

import logging
from typing import Optional

from .sibling import postprocess as sibling_postprocess
from .stepmother import postprocess as stepmother_postprocess
from .stepfather import postprocess as stepfather_postprocess
from .grandmother import postprocess as grandmother_postprocess
from .dog_baron import postprocess as dog_baron_postprocess
from .common import split_event_section

logger = logging.getLogger(__name__)


def phase_to_level(phase_id: Optional[str], npc_phases: Optional[list] = None) -> int:
    """phase_id와 phases 리스트에서 후처리 레벨(1~3)을 결정한다.

    phases 리스트 내 위치(0-indexed)를 레벨로 변환:
    - index 0 (첫 번째 phase / A) → 1 (정상)
    - index 1 (두 번째 phase / B) → 2 (혼란 / 중간 광기)
    - index 2 이상 (세 번째+ / C) → 3 (인형화 / 완전 광기)
    """
    if not phase_id or not npc_phases:
        return 1
    phase_ids = [p.get("phase_id", "") for p in npc_phases]
    try:
        return min(phase_ids.index(phase_id) + 1, 3)
    except ValueError:
        return 1


def _apply_character_postprocess(
    text: str,
    npc_id: str,
    level: int,
    seed: Optional[int] = None,
) -> str:
    """캐릭터별 후처리 함수를 호출한다."""
    if npc_id == "brother":
        return sibling_postprocess(text, glitch_level=level, seed=seed)
    elif npc_id == "stepmother":
        return stepmother_postprocess(text, monstrosity=level, seed=seed)
    elif npc_id == "stepfather":
        return stepfather_postprocess(text, suppression_level=level, seed=seed)
    elif npc_id == "grandmother":
        return grandmother_postprocess(text, lucidity_level=level, seed=seed)
    elif npc_id == "dog_baron":
        return dog_baron_postprocess(text, loyalty_level=level, seed=seed)
    else:
        return text


def postprocess_npc_dialogue(
    text: str,
    npc_id: str,
    phase_id: Optional[str] = None,
    npc_phases: Optional[list] = None,
    seed: Optional[int] = None,
) -> str:
    """npc_id에 따라 적절한 후처리기를 선택하여 적용한다.

    전체 텍스트를 대사로 간주하고 캐릭터 효과를 적용한다.
    사건(사건:) 섹션은 후처리에서 완전히 제외된다.

    Args:
        text: 원본 LLM 출력
        npc_id: NPC 식별자 ("brother", "stepmother", "stepfather", "grandmother", "dog_baron")
        phase_id: NPC의 현재 phase ID (NPCState.current_phase_id)
        npc_phases: NPC phases 리스트 (YAML phases 필드)
            - phase 순서로 후처리 레벨(1~3)을 결정: A→1, B→2, C→3
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    level = phase_to_level(phase_id, npc_phases)
    logger.info(f"[postprocess] npc={npc_id} | phase={phase_id} → level={level}")
    logger.debug(f"[postprocess] raw={text[:80]}")

    # 사건 섹션 분리 (후처리 대상에서 제외)
    main_text, event_text = split_event_section(text)

    # 전체 텍스트를 대사로 간주하여 캐릭터 효과 적용
    result = _apply_character_postprocess(main_text, npc_id, level, seed)

    # 사건 섹션 재결합
    if event_text:
        result = result.rstrip() + "\n사건: " + event_text

    logger.debug(f"[postprocess] processed={result[:80]}")
    return result
