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
from .common import split_event_section, parse_text_segments, normalize_description

logger = logging.getLogger(__name__)


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
    humanity: int = 100,
    seed: Optional[int] = None,
) -> str:
    """npc_id에 따라 적절한 후처리기를 선택하여 적용한다.

    소설체 혼합 형식(따옴표 대사 + 서술)이 감지되면 대사 파트에만 캐릭터 효과를
    적용하고, 서술 파트는 광기 아티팩트를 정규화하여 클린하게 유지한다.
    사건(사건:) 섹션은 후처리에서 완전히 제외된다.

    Args:
        text: 원본 LLM 출력
        npc_id: NPC 식별자 ("brother", "stepmother", "stepfather", "grandmother", "dog_baron")
        humanity: NPC의 humanity 스탯 (0~100)
            - stepfather: 높을수록 기억 혼란, 낮을수록 로봇화
            - grandmother: 높을수록 명료(생기 공유 후), 낮을수록 혼수
            - dog_baron: 높을수록 우호적, 낮을수록 적대적
        seed: 랜덤 시드 (재현이 필요할 때)

    Returns:
        후처리된 문자열
    """
    level = humanity_to_level(humanity)
    logger.debug(f"npc_id={npc_id} | humanity={humanity} → level={level} | raw={text[:80]}")

    # 사건 섹션 분리 (후처리 대상에서 제외)
    main_text, event_text = split_event_section(text)

    # 세그먼트 분석
    segments = parse_text_segments(main_text)
    types = {seg_type for seg_type, _ in segments}
    is_mixed = 'dialogue' in types and 'description' in types

    if is_mixed:
        # 소설체 혼합 형식: 대사만 후처리, 서술은 정규화
        parts = []
        for seg_type, content in segments:
            if seg_type == 'dialogue':
                processed = _apply_character_postprocess(content, npc_id, level, seed)
                parts.append(f'"{processed}"')
            else:
                parts.append(normalize_description(content))
        result = "".join(parts)
    else:
        # 순수 대사 형식: 전체 후처리 (기존 동작)
        result = _apply_character_postprocess(main_text, npc_id, level, seed)

    # 사건 섹션 재결합
    if event_text:
        result = result.rstrip() + "\n사건: " + event_text

    logger.debug(f"npc_id={npc_id} | processed={result[:80]}")
    return result
