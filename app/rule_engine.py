"""
app/rule_engine.py
Rule Engine - memory_rules.yaml 기반 상태 변화 처리

Intent에 따라 자동으로 적용되는 규칙들을 처리합니다.
- investigate: 조사 → 의심도 증가, 인간성 회복
- obey: 복종 → 호감도 증가, 인간성 감소
- rebel: 반항 → 호감도 감소, 의심도 급증
- reveal: 진실 폭로 → NPC 인간성 회복
- summarize: 하루 정리 → 인간성 회복
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def apply_memory_rules(
    intent: str,
    memory_rules: Dict[str, Any],
    active_npc_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Intent에 따라 memory_rules의 rewrite_rules를 적용합니다.

    Args:
        intent: 플레이어 행동 의도 ("investigate", "obey", "rebel", "reveal", "summarize", "neutral")
        memory_rules: memory_rules.yaml 내용
        active_npc_id: 현재 상호작용 중인 NPC ID (선택적)

    Returns:
        state_delta: 상태 변화 딕셔너리
        {
            "vars": {"humanity": 1, "suspicion_level": 2},
            "npc_stats": {"stepmother": {"trust": -10}},
        }
    """
    delta: Dict[str, Any] = {
        "vars": {},
        "npc_stats": {},
    }

    if not memory_rules or "rewrite_rules" not in memory_rules:
        logger.debug("[RuleEngine] memory_rules가 비어있음, 빈 delta 반환")
        return delta

    rules = memory_rules.get("rewrite_rules", [])

    for rule in rules:
        rule_id = rule.get("rule_id", "unknown")
        when_condition = rule.get("when", "")
        effects = rule.get("effects", [])

        # 조건 평가
        if _evaluate_condition(when_condition, intent):
            logger.info(f"[RuleEngine] 규칙 적용: {rule_id} (intent={intent})")

            for effect in effects:
                _apply_effect(effect, delta, active_npc_id)

    return delta


def _evaluate_condition(when_condition: str, intent: str) -> bool:
    """
    when 조건을 평가합니다.

    현재 지원하는 조건 형식:
    - "intent == 'investigate'"
    - "intent == 'obey'"
    - 복합 조건: "intent == 'reveal' and has_item(real_family_photo)"

    TODO: has_item, world_state 조건 지원 확장
    """
    if not when_condition:
        return False

    # 단순 intent 매칭
    intent_match = re.search(r"intent\s*==\s*['\"](\w+)['\"]", when_condition)
    if intent_match:
        required_intent = intent_match.group(1)
        return intent == required_intent

    return False


def _apply_effect(
    effect: Dict[str, Any],
    delta: Dict[str, Any],
    active_npc_id: Optional[str] = None,
) -> None:
    """
    개별 effect를 delta에 적용합니다.

    지원하는 effect 타입:
    - var_add: 변수 증가 (key, value)
    - var_sub: 변수 감소 (key, value)
    - npc_stat_add: NPC 스탯 증가 (npc, stat, value)
    - npc_stat_sub: NPC 스탯 감소 (npc, stat, value)
    - set_state: 상태 설정 (target, value)
    """
    effect_type = effect.get("type", "")

    # var_add / var_sub
    if effect_type == "var_add":
        key = effect.get("key", "")
        value = effect.get("value", 0)
        var_name = _extract_var_name(key)
        if var_name:
            delta["vars"][var_name] = delta["vars"].get(var_name, 0) + value
            logger.debug(f"[RuleEngine] var_add: {var_name} += {value}")

    elif effect_type == "var_sub":
        key = effect.get("key", "")
        value = effect.get("value", 0)
        var_name = _extract_var_name(key)
        if var_name:
            delta["vars"][var_name] = delta["vars"].get(var_name, 0) - value
            logger.debug(f"[RuleEngine] var_sub: {var_name} -= {value}")

    # npc_stat_add / npc_stat_sub
    elif effect_type == "npc_stat_add":
        npc_id = _resolve_npc_id(effect.get("npc", ""), active_npc_id)
        stat = effect.get("stat", "")
        value = effect.get("value", 0)
        if npc_id and stat:
            if npc_id not in delta["npc_stats"]:
                delta["npc_stats"][npc_id] = {}
            delta["npc_stats"][npc_id][stat] = delta["npc_stats"][npc_id].get(stat, 0) + value
            logger.debug(f"[RuleEngine] npc_stat_add: {npc_id}.{stat} += {value}")

    elif effect_type == "npc_stat_sub":
        npc_id = _resolve_npc_id(effect.get("npc", ""), active_npc_id)
        stat = effect.get("stat", "")
        value = effect.get("value", 0)
        if npc_id and stat:
            if npc_id not in delta["npc_stats"]:
                delta["npc_stats"][npc_id] = {}
            delta["npc_stats"][npc_id][stat] = delta["npc_stats"][npc_id].get(stat, 0) - value
            logger.debug(f"[RuleEngine] npc_stat_sub: {npc_id}.{stat} -= {value}")

    # 알 수 없는 타입
    else:
        logger.warning(f"[RuleEngine] 알 수 없는 effect 타입: {effect_type}")


def _extract_var_name(key: str) -> Optional[str]:
    """
    "vars.humanity" 형식에서 "humanity"를 추출합니다.
    "flags.truth_revealed" 형식도 지원합니다.
    """
    if key.startswith("vars."):
        return key[5:]
    elif key.startswith("flags."):
        return key[6:]
    return key if key else None


def _resolve_npc_id(npc_ref: str, active_npc_id: Optional[str]) -> Optional[str]:
    """
    NPC 참조를 실제 ID로 변환합니다.

    - "__active__": 현재 상호작용 중인 NPC
    - 그 외: 그대로 반환
    """
    if npc_ref == "__active__":
        return active_npc_id
    return npc_ref if npc_ref else None


def merge_rule_delta(
    tool_delta: Dict[str, Any],
    rule_delta: Dict[str, Any],
    include_turn_increment: bool = True,
) -> Dict[str, Any]:
    """
    Tool의 delta와 Rule Engine의 delta를 병합합니다.

    Args:
        tool_delta: Tool 실행 결과 delta
        rule_delta: Rule Engine 적용 결과 delta
        include_turn_increment: 턴 증가 포함 여부 (낮 턴에서 True)

    Returns:
        병합된 delta
    """
    merged = {
        "vars": {},
        "npc_stats": {},
        "turn_increment": 1 if include_turn_increment else 0,
    }

    # vars 병합 (누적)
    for key, value in tool_delta.get("vars", {}).items():
        merged["vars"][key] = merged["vars"].get(key, 0) + value

    for key, value in rule_delta.get("vars", {}).items():
        merged["vars"][key] = merged["vars"].get(key, 0) + value

    # npc_stats 병합 (누적)
    for npc_id, stats in tool_delta.get("npc_stats", {}).items():
        if npc_id not in merged["npc_stats"]:
            merged["npc_stats"][npc_id] = {}
        for stat, value in stats.items():
            merged["npc_stats"][npc_id][stat] = merged["npc_stats"][npc_id].get(stat, 0) + value

    for npc_id, stats in rule_delta.get("npc_stats", {}).items():
        if npc_id not in merged["npc_stats"]:
            merged["npc_stats"][npc_id] = {}
        for stat, value in stats.items():
            merged["npc_stats"][npc_id][stat] = merged["npc_stats"][npc_id].get(stat, 0) + value

    # 기타 필드는 tool_delta 우선
    for key in tool_delta:
        if key not in ("vars", "npc_stats"):
            merged[key] = tool_delta[key]

    return merged
