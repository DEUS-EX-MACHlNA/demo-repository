"""
test/test_condition_eval.py
ConditionEvaluator 전체 분기 테스트

조건 평가기가 지원하는 모든 패턴을 검증합니다:
  - 리터럴(true/false)
  - NPC stat (숫자/문자열)
  - vars (숫자/불리언)
  - flags (null/bool)
  - locks
  - has_item
  - system.turn / system.turn == turn_limit
  - AND / OR 조합
  - area / system.phase / target 패턴
"""
import pytest

from app.condition_eval import ConditionEvaluator, evaluate_condition
from app.schemas.game_state import NPCState, WorldStatePipeline
from app.schemas.condition import EvalContext
from app.schemas.status import NPCStatus

from test.conftest import make_initial_world, make_stepmother, make_brother, make_dog_baron


@pytest.fixture
def evaluator():
    return ConditionEvaluator()


@pytest.fixture
def ctx(initial_world):
    """기본 EvalContext"""
    return EvalContext(world_state=initial_world, turn_limit=50)


# ============================================================
# 리터럴
# ============================================================
class TestLiteral:
    def test_true(self, evaluator, ctx):
        assert evaluator.evaluate("true", ctx) is True

    def test_false(self, evaluator, ctx):
        assert evaluator.evaluate("false", ctx) is False

    def test_empty_string(self, evaluator, ctx):
        assert evaluator.evaluate("", ctx) is False

    def test_whitespace(self, evaluator, ctx):
        assert evaluator.evaluate("  true  ", ctx) is True


# ============================================================
# NPC stat 숫자 비교
# ============================================================
class TestNpcStatNumeric:
    """npc.{npc_id}.{stat} {op} {value}"""

    def test_affection_gte_exact(self, evaluator, ctx):
        # brother.affection == 50 (초기값)
        assert evaluator.evaluate("npc.brother.affection >= 50", ctx) is True

    def test_affection_gte_above(self, evaluator, ctx):
        assert evaluator.evaluate("npc.brother.affection >= 51", ctx) is False

    def test_affection_lte(self, evaluator, ctx):
        assert evaluator.evaluate("npc.brother.affection <= 50", ctx) is True

    def test_affection_gt(self, evaluator, ctx):
        assert evaluator.evaluate("npc.brother.affection > 49", ctx) is True

    def test_affection_lt(self, evaluator, ctx):
        assert evaluator.evaluate("npc.brother.affection < 51", ctx) is True

    def test_affection_eq(self, evaluator, ctx):
        assert evaluator.evaluate("npc.brother.affection == 50", ctx) is True

    def test_affection_neq(self, evaluator, ctx):
        assert evaluator.evaluate("npc.brother.affection != 99", ctx) is True

    def test_nonexistent_npc(self, evaluator, ctx):
        assert evaluator.evaluate("npc.ghost.affection >= 0", ctx) is False

    def test_nonexistent_stat_defaults_zero(self, evaluator, ctx):
        assert evaluator.evaluate("npc.brother.nonexistent == 0", ctx) is True

    def test_stepmother_affection(self, evaluator, ctx):
        # stepmother.affection == 50
        assert evaluator.evaluate("npc.stepmother.affection >= 50", ctx) is True

    def test_grandmother_low_affection(self, evaluator, ctx):
        # grandmother.affection == 20
        assert evaluator.evaluate("npc.grandmother.affection >= 50", ctx) is False

    def test_dog_baron_high_affection(self, evaluator, ctx):
        # dog_baron.affection == 70
        assert evaluator.evaluate("npc.dog_baron.affection >= 70", ctx) is True
        assert evaluator.evaluate("npc.dog_baron.affection >= 90", ctx) is False

    @pytest.mark.parametrize("npc_id,stat,initial", [
        ("stepmother", "affection", 50),
        ("stepmother", "humanity", 100),
        ("stepfather", "affection", 30),
        ("stepfather", "humanity", 20),
        ("brother", "affection", 50),
        ("brother", "humanity", 50),
        ("grandmother", "affection", 20),
        ("grandmother", "humanity", 10),
        ("dog_baron", "affection", 70),
        ("dog_baron", "humanity", 100),
    ])
    def test_all_initial_stats(self, evaluator, ctx, npc_id, stat, initial):
        assert evaluator.evaluate(f"npc.{npc_id}.{stat} == {initial}", ctx) is True


# ============================================================
# NPC stat 문자열 비교 (status)
# ============================================================
class TestNpcStatString:
    """npc.{npc_id}.{stat} == '{string}'"""

    def test_status_alive(self, evaluator):
        world = make_initial_world()
        ctx = EvalContext(world_state=world, turn_limit=50)
        # NPCState.stats에 status가 아닌 NPCState.status로 저장됨
        # condition_eval은 stats에서 먼저 찾고 없으면 memory에서 찾음
        # 하지만 실제 status는 NPCState.status 필드에 있음
        # → 현재 구현에서 npc.stepmother.status == 'alive'가 어떻게 평가되는지 확인
        # stats에 "status" 키를 넣어서 테스트
        world.npcs["stepmother"].stats["status"] = "sleeping"
        assert evaluator.evaluate("npc.stepmother.status == 'sleeping'", ctx) is True

    def test_status_not_match(self, evaluator):
        world = make_initial_world()
        world.npcs["stepmother"].stats["status"] = "alive"
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("npc.stepmother.status == 'sleeping'", ctx) is False

    def test_status_missing(self, evaluator):
        world = make_initial_world()
        world.npcs["stepmother"].stats["status"] = "missing"
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("npc.stepmother.status == 'missing'", ctx) is True


# ============================================================
# vars 숫자 비교
# ============================================================
class TestVarsNumeric:
    """vars.{var_name} {op} {value}"""

    def test_humanity_initial(self, evaluator, ctx):
        assert evaluator.evaluate("vars.humanity == 100", ctx) is True

    def test_humanity_lte_zero(self, evaluator):
        world = make_initial_world(vars={"humanity": 0, "suspicion_level": 0, "day": 1, "status_effects": []})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("vars.humanity <= 0", ctx) is True

    def test_suspicion_gte_100(self, evaluator):
        world = make_initial_world(vars={"humanity": 50, "suspicion_level": 100, "day": 3, "status_effects": []})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("vars.suspicion_level >= 100", ctx) is True

    def test_suspicion_initial_zero(self, evaluator, ctx):
        assert evaluator.evaluate("vars.suspicion_level >= 100", ctx) is False

    def test_day_gte_2(self, evaluator):
        world = make_initial_world(vars={"humanity": 100, "suspicion_level": 0, "day": 2, "status_effects": []})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("vars.day >= 2", ctx) is True

    def test_day_initial_lt_2(self, evaluator, ctx):
        assert evaluator.evaluate("vars.day >= 2", ctx) is False

    @pytest.mark.parametrize("op,val,expected", [
        (">=", 100, True),
        ("<=", 100, True),
        ("==", 100, True),
        (">", 99, True),
        ("<", 101, True),
        ("!=", 50, True),
        (">", 100, False),
        ("<", 100, False),
    ])
    def test_humanity_operators(self, evaluator, ctx, op, val, expected):
        assert evaluator.evaluate(f"vars.humanity {op} {val}", ctx) is expected


# ============================================================
# vars 불리언
# ============================================================
class TestVarsBool:
    """vars.{var_name} == true/false"""

    def test_vars_bool_true(self, evaluator):
        world = make_initial_world(vars={"humanity": 100, "suspicion_level": 0, "day": 1,
                                          "discovered": True, "status_effects": []})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("vars.discovered == true", ctx) is True

    def test_vars_bool_false(self, evaluator):
        world = make_initial_world(vars={"humanity": 100, "suspicion_level": 0, "day": 1,
                                          "discovered": False, "status_effects": []})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("vars.discovered == false", ctx) is True

    def test_vars_bool_missing_defaults_false(self, evaluator, ctx):
        assert evaluator.evaluate("vars.nonexistent == false", ctx) is True


# ============================================================
# flags
# ============================================================
class TestFlags:
    """flags.{flag} == null / true / false"""

    def test_ending_null(self, evaluator, ctx):
        assert evaluator.evaluate("flags.ending == null", ctx) is True

    def test_ending_not_null(self, evaluator):
        world = make_initial_world(flags={"ending": "stealth_exit", "brother_sacrifice": False,
                                           "stepmother_away": False, "oil_on_stepmother": False,
                                           "house_on_fire": False})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("flags.ending == null", ctx) is False

    def test_brother_sacrifice_false(self, evaluator, ctx):
        assert evaluator.evaluate("flags.brother_sacrifice == false", ctx) is True

    def test_brother_sacrifice_true(self, evaluator):
        world = make_initial_world(flags={"ending": None, "brother_sacrifice": True,
                                           "stepmother_away": False, "oil_on_stepmother": False,
                                           "house_on_fire": False})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("flags.brother_sacrifice == true", ctx) is True

    def test_oil_on_stepmother(self, evaluator):
        world = make_initial_world(flags={"ending": None, "brother_sacrifice": False,
                                           "stepmother_away": False, "oil_on_stepmother": True,
                                           "house_on_fire": False})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("flags.oil_on_stepmother == true", ctx) is True

    def test_house_on_fire(self, evaluator):
        world = make_initial_world(flags={"ending": None, "brother_sacrifice": False,
                                           "stepmother_away": False, "oil_on_stepmother": True,
                                           "house_on_fire": True})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("flags.house_on_fire == true", ctx) is True

    def test_nonexistent_flag_defaults_false(self, evaluator, ctx):
        assert evaluator.evaluate("flags.nonexistent == false", ctx) is True


# ============================================================
# locks
# ============================================================
class TestLocks:
    """locks.{lock_id} == true/false"""

    def test_lock_not_unlocked(self, evaluator, ctx):
        assert evaluator.evaluate("locks.quest_escape_route == true", ctx) is False

    def test_lock_unlocked(self, evaluator):
        world = make_initial_world(locks={"quest_escape_route": True})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("locks.quest_escape_route == true", ctx) is True

    def test_lock_false(self, evaluator):
        world = make_initial_world(locks={"quest_escape_route": False})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("locks.quest_escape_route == false", ctx) is True

    @pytest.mark.parametrize("lock_id", [
        "quest_escape_route",
        "quest_fire_weakness",
        "quest_brother_sacrifice",
        "hint_sedative",
        "hint_oil_bottle",
        "hint_dried_herbs",
    ])
    def test_all_locks_initially_false(self, evaluator, ctx, lock_id):
        assert evaluator.evaluate(f"locks.{lock_id} == true", ctx) is False


# ============================================================
# has_item
# ============================================================
class TestHasItem:
    """has_item({item_id})"""

    def test_has_warm_black_tea(self, evaluator, ctx):
        assert evaluator.evaluate("has_item(warm_black_tea)", ctx) is True

    def test_not_has_secret_key(self, evaluator, ctx):
        assert evaluator.evaluate("has_item(secret_key)", ctx) is False

    @pytest.mark.parametrize("item_id,expected", [
        ("warm_black_tea", True),   # 시작 아이템
        ("secret_key", False),
        ("industrial_sedative", False),
        ("lighter", False),
        ("oil_bottle", False),
        ("real_family_photo", False),
        ("dried_herbs", False),
        ("dog_treat", False),
        ("lubricant_oil", False),
    ])
    def test_initial_inventory(self, evaluator, ctx, item_id, expected):
        assert evaluator.evaluate(f"has_item({item_id})", ctx) is expected


# ============================================================
# system.turn
# ============================================================
class TestSystemTurn:
    """system.turn {op} {value} / system.turn == turn_limit"""

    def test_turn_initial(self, evaluator, ctx):
        assert evaluator.evaluate("system.turn == 1", ctx) is True

    def test_turn_gte(self, evaluator):
        world = make_initial_world(turn=40)
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("system.turn >= 40", ctx) is True

    def test_turn_limit(self, evaluator):
        world = make_initial_world(turn=50)
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("system.turn == turn_limit", ctx) is True

    def test_turn_not_limit(self, evaluator):
        world = make_initial_world(turn=49)
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("system.turn == turn_limit", ctx) is False


# ============================================================
# AND / OR 조합
# ============================================================
class TestLogicalCombinations:
    """and / or 연산자"""

    def test_and_both_true(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity == 100 and npc.brother.affection >= 50", ctx
        ) is True

    def test_and_first_false(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity <= 0 and npc.brother.affection >= 50", ctx
        ) is False

    def test_and_second_false(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity == 100 and npc.brother.affection >= 99", ctx
        ) is False

    def test_and_both_false(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity <= 0 and npc.brother.affection >= 99", ctx
        ) is False

    def test_or_both_true(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity == 100 or npc.brother.affection >= 50", ctx
        ) is True

    def test_or_first_true(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity == 100 or vars.suspicion_level >= 100", ctx
        ) is True

    def test_or_second_true(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity <= 0 or npc.brother.affection >= 50", ctx
        ) is True

    def test_or_both_false(self, evaluator, ctx):
        assert evaluator.evaluate(
            "vars.humanity <= 0 or vars.suspicion_level >= 100", ctx
        ) is False

    def test_has_item_and_npc(self, evaluator, ctx):
        assert evaluator.evaluate(
            "has_item(warm_black_tea) and npc.dog_baron.affection >= 70", ctx
        ) is True

    def test_complex_stealth_exit_condition(self, evaluator):
        """stealth_exit 엔딩 조건 직접 평가"""
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
        )
        world.npcs["stepmother"].stats["status"] = "sleeping"
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate(
            "has_item(secret_key) and npc.stepmother.status == 'sleeping'", ctx
        ) is True

    def test_complex_sibling_sacrifice_condition(self, evaluator):
        """sibling_sacrifice 엔딩 조건 직접 평가"""
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
            flags={"ending": None, "brother_sacrifice": True,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
        )
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate(
            "has_item(secret_key) and flags.brother_sacrifice == true", ctx
        ) is True

    def test_eternal_dinner_condition(self, evaluator):
        """eternal_dinner 엔딩 조건 직접 평가"""
        world = make_initial_world(
            turn=50,
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
        )
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate(
            "system.turn == turn_limit and flags.ending == null", ctx
        ) is True


# ============================================================
# target / area / phase 패턴
# ============================================================
class TestSpecialPatterns:
    def test_target_eq(self, evaluator):
        world = make_initial_world()
        ctx = EvalContext(world_state=world, turn_limit=50, extra_vars={"target_npc_id": "stepmother"})
        assert evaluator.evaluate("target == 'stepmother'", ctx) is True
        assert evaluator.evaluate("target == 'brother'", ctx) is False

    def test_npc_target_id(self, evaluator):
        world = make_initial_world()
        ctx = EvalContext(world_state=world, turn_limit=50, extra_vars={"target_npc_id": "brother"})
        assert evaluator.evaluate("npc.target.id == 'brother'", ctx) is True
        assert evaluator.evaluate("npc.target.id != 'stepmother'", ctx) is True

    def test_npc_target_stat(self, evaluator):
        world = make_initial_world()
        ctx = EvalContext(world_state=world, turn_limit=50, extra_vars={"target_npc_id": "brother"})
        assert evaluator.evaluate("npc.target.affection >= 50", ctx) is True
        assert evaluator.evaluate("npc.target.affection >= 99", ctx) is False

    def test_area_current(self, evaluator):
        world = make_initial_world(vars={"humanity": 100, "suspicion_level": 0, "day": 1,
                                          "current_area": "kitchen", "status_effects": []})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("area.current == 'kitchen'", ctx) is True
        assert evaluator.evaluate("area.current == 'garden'", ctx) is False

    def test_system_phase(self, evaluator):
        world = make_initial_world(vars={"humanity": 100, "suspicion_level": 0, "day": 1,
                                          "current_phase": "evening_prep", "status_effects": []})
        ctx = EvalContext(world_state=world, turn_limit=50)
        assert evaluator.evaluate("system.phase == 'evening_prep'", ctx) is True

    def test_unknown_condition_returns_false(self, evaluator, ctx):
        assert evaluator.evaluate("some.unknown.pattern", ctx) is False


# ============================================================
# 편의 함수
# ============================================================
class TestConvenienceFunction:
    def test_evaluate_condition_wrapper(self, initial_world):
        assert evaluate_condition("true", initial_world) is True
        assert evaluate_condition("vars.humanity == 100", initial_world) is True
        assert evaluate_condition("has_item(secret_key)", initial_world) is False
