"""
app/condition_eval.py
공용 조건 평가기 — LockManager, EndingChecker 등에서 공통 사용

조건 문자열을 파싱하고 WorldState 기반으로 평가합니다.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.schemas import WorldState

logger = logging.getLogger(__name__)


class EvalContext(BaseModel):
    """조건 평가에 필요한 컨텍스트"""
    world_state: WorldState
    turn_limit: int = 50
    extra_vars: Dict[str, Any] = Field(default_factory=dict)


class ConditionEvaluator:
    """
    조건 문자열 평가기

    지원하는 조건 형식:
    - npc.{npc_id}.{stat} {op} {value}     (예: npc.brother.affection >= 70)
    - npc.{npc_id}.{stat} == '{string}'    (예: npc.stepmother.status == 'sleeping')
    - vars.{var_name} {op} {value}         (예: vars.humanity <= 60)
    - vars.{var_name} == true/false        (예: vars.house_on_fire == true)
    - flags.{flag_name} == true/false/null (예: flags.ending == null)
    - has_item({item_id})                  (예: has_item(real_family_photo))
    - system.turn {op} {value}             (예: system.turn >= 40)
    - system.turn == turn_limit            (예: system.turn == turn_limit)
    - AND 조합                             (예: vars.humanity <= 60 and has_item(photo))
    """

    def evaluate(
        self,
        condition: str,
        context: EvalContext,
    ) -> bool:
        """
        조건 문자열을 평가합니다.

        Args:
            condition: 조건 문자열
            context: 평가 컨텍스트 (WorldState, turn_limit 등)

        Returns:
            조건 충족 여부
        """
        if not condition:
            return False

        # AND로 분리된 조건들 처리
        if " and " in condition:
            parts = condition.split(" and ")
            return all(self._evaluate_single(p.strip(), context) for p in parts)

        return self._evaluate_single(condition, context)

    def _evaluate_single(
        self,
        condition: str,
        context: EvalContext,
    ) -> bool:
        """단일 조건 평가"""
        world_state = context.world_state

        # 1. has_item(item_id) 패턴
        has_item_match = re.match(r'has_item\((\w+)\)', condition)
        if has_item_match:
            item_id = has_item_match.group(1)
            return item_id in world_state.inventory

        # 2. npc.{npc_id}.{stat} == '{string}' 패턴 (문자열 비교)
        npc_str_match = re.match(
            r"npc\.(\w+)\.(\w+)\s*==\s*'([^']*)'",
            condition
        )
        if npc_str_match:
            npc_id = npc_str_match.group(1)
            stat = npc_str_match.group(2)
            expected = npc_str_match.group(3)

            npc_state = world_state.npcs.get(npc_id)
            if not npc_state:
                return False

            # NPCState의 stats에서 조회
            current = npc_state.stats.get(stat)
            if current is None:
                current = npc_state.memory.get(stat, "")
            return str(current) == expected

        # 3. npc.{npc_id}.{stat} {op} {value} 패턴 (숫자 비교)
        npc_num_match = re.match(
            r'npc\.(\w+)\.(\w+)\s*(>=|<=|==|>|<|!=)\s*(\d+)',
            condition
        )
        if npc_num_match:
            npc_id = npc_num_match.group(1)
            stat = npc_num_match.group(2)
            op = npc_num_match.group(3)
            value = int(npc_num_match.group(4))

            npc_state = world_state.npcs.get(npc_id)
            if not npc_state:
                return False

            # NPCState의 stats에서 조회
            current = npc_state.stats.get(stat, 0)
            return self._compare(current, op, value)

        # 4. vars.{var_name} == true/false 패턴 (불리언)
        vars_bool_match = re.match(
            r'vars\.(\w+)\s*==\s*(true|false)',
            condition
        )
        if vars_bool_match:
            var_name = vars_bool_match.group(1)
            expected = vars_bool_match.group(2) == "true"

            current = world_state.vars.get(var_name, False)
            return current == expected

        # 5. vars.{var_name} {op} {value} 패턴 (숫자)
        vars_num_match = re.match(
            r'vars\.(\w+)\s*(>=|<=|==|>|<|!=)\s*(\d+)',
            condition
        )
        if vars_num_match:
            var_name = vars_num_match.group(1)
            op = vars_num_match.group(2)
            value = int(vars_num_match.group(3))

            current = world_state.vars.get(var_name, 0)
            if isinstance(current, bool):
                current = 1 if current else 0
            return self._compare(current, op, value)

        # 6. flags.{flag_name} == null 패턴
        flags_null_match = re.match(
            r'flags\.(\w+)\s*==\s*null',
            condition
        )
        if flags_null_match:
            flag_name = flags_null_match.group(1)
            current = world_state.flags.get(flag_name)
            # vars에서도 찾아봄 (ending은 vars에 저장될 수 있음)
            if current is None:
                current = world_state.vars.get(flag_name)
            return current is None

        # 7. flags.{flag_name} == true/false 패턴
        flags_bool_match = re.match(
            r'flags\.(\w+)\s*==\s*(true|false)',
            condition
        )
        if flags_bool_match:
            flag_name = flags_bool_match.group(1)
            expected = flags_bool_match.group(2) == "true"

            current = world_state.flags.get(flag_name, False)
            return current == expected

        # 8. system.turn == turn_limit 패턴 (특수 케이스)
        if condition.strip() == "system.turn == turn_limit":
            return world_state.turn == context.turn_limit

        # 9. system.{field} {op} {value} 패턴
        system_match = re.match(
            r'system\.(\w+)\s*(>=|<=|==|>|<|!=)\s*(\d+)',
            condition
        )
        if system_match:
            field = system_match.group(1)
            op = system_match.group(2)
            value = int(system_match.group(3))

            if field == "turn":
                current = world_state.turn
            else:
                current = 0
            return self._compare(current, op, value)

        logger.warning(f"[ConditionEvaluator] 알 수 없는 조건 형식: {condition}")
        return False

    def _compare(self, current: Union[int, float], op: str, value: Union[int, float]) -> bool:
        """비교 연산 수행"""
        if op == ">=":
            return current >= value
        elif op == "<=":
            return current <= value
        elif op == "==":
            return current == value
        elif op == ">":
            return current > value
        elif op == "<":
            return current < value
        elif op == "!=":
            return current != value
        return False


# ============================================================
# 싱글턴
# ============================================================
_evaluator_instance: Optional[ConditionEvaluator] = None


def get_condition_evaluator() -> ConditionEvaluator:
    """ConditionEvaluator 싱글턴 인스턴스 반환"""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = ConditionEvaluator()
    return _evaluator_instance


# ============================================================
# 편의 함수
# ============================================================
def evaluate_condition(
    condition: str,
    world_state: WorldState,
    turn_limit: int = 50,
) -> bool:
    """
    조건 평가 편의 함수

    Args:
        condition: 조건 문자열
        world_state: 현재 월드 상태
        turn_limit: 시나리오 turn_limit

    Returns:
        조건 충족 여부
    """
    evaluator = get_condition_evaluator()
    context = EvalContext(world_state=world_state, turn_limit=turn_limit)
    return evaluator.evaluate(condition, context)


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    import logging
    from app.schemas import NPCState, WorldState

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("CONDITION EVALUATOR 테스트")
    print("=" * 60)

    # 테스트용 월드 상태 생성
    world = WorldState(
        turn=5,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 7, "fear": 3, "suspicion": 4}
            ),
            "button_father": NPCState(
                npc_id="button_father",
                stats={"trust": 2, "fear": 8, "suspicion": 9}
            ),
        },
        inventory=["item_button", "item_thread"],
        vars={"humanity": 45, "total_suspicion": 13, "discovered": True},
        flags={"ending_flag": "stealth"},
    )

    print(f"\n[1] 월드 상태:")
    print(f"  - turn: {world.turn}")
    print(f"  - npcs: {list(world.npcs.keys())}")
    print(f"  - inventory: {world.inventory}")
    print(f"  - vars: {world.vars}")
    print(f"  - flags: {world.flags}")

    # 테스트 케이스
    test_cases = [
        # NPC stat 조건
        ("npc.button_mother.trust >= 5", True, "NPC trust >= 5"),
        ("npc.button_father.fear > 7", True, "NPC fear > 7"),
        ("npc.button_mother.suspicion <= 5", True, "NPC suspicion <= 5"),

        # vars 조건
        ("vars.humanity <= 50", True, "humanity <= 50"),
        ("vars.total_suspicion >= 10", True, "total_suspicion >= 10"),
        ("vars.humanity > 60", False, "humanity > 60 (should fail)"),

        # vars 불리언
        ("vars.discovered == true", True, "discovered == true"),

        # inventory 조건 (has_item 함수 형식)
        ("has_item(item_button)", True, "has item_button"),
        ("has_item(item_needle)", False, "has item_needle (should fail)"),

        # system.turn 조건
        ("system.turn >= 3", True, "system.turn >= 3"),
        ("system.turn <= 10", True, "system.turn <= 10"),
        ("system.turn == 5", True, "system.turn == 5"),

        # AND 조건 (소문자 'and' 사용)
        ("vars.humanity <= 50 and system.turn >= 3", True, "AND condition"),
        ("vars.humanity > 60 and system.turn >= 3", False, "AND condition (should fail)"),

        # 복합 조건
        ("has_item(item_button) and vars.humanity <= 50", True, "has_item AND vars"),
    ]

    print(f"\n[2] 조건 평가 테스트 ({len(test_cases)}개):")
    print("-" * 60)

    passed = 0
    failed = 0

    for condition, expected, description in test_cases:
        result = evaluate_condition(condition, world, turn_limit=50)
        status = "✓" if result == expected else "✗"

        if result == expected:
            passed += 1
            print(f"  {status} {description}")
            print(f"     조건: {condition}")
            print(f"     결과: {result} (예상: {expected})")
        else:
            failed += 1
            print(f"  {status} {description} [FAILED]")
            print(f"     조건: {condition}")
            print(f"     결과: {result} (예상: {expected})")

    print("\n" + "=" * 60)
    print(f"결과: {passed}개 통과, {failed}개 실패")
    print("=" * 60)
