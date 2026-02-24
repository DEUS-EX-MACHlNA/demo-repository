"""
test/test_ending_checker.py
EndingChecker 전체 분기 테스트

6개 엔딩 각각에 대해:
  1. 조건 충족 시 정확히 해당 엔딩이 트리거되는지
  2. 조건 미충족 시 트리거되지 않는지
  3. 경계값(boundary)에서 정확히 동작하는지
  4. skip_has_item 옵션 동작 검증
  5. 엔딩 우선순위 (YAML 순서) 검증

엔딩 정의 순서 (scenario.yaml):
  1. stealth_exit      - has_item(secret_key) and npc.stepmother.status == 'sleeping'
  2. chaotic_breakout   - flags.house_on_fire == true
  3. sibling_sacrifice  - has_item(secret_key) and flags.brother_sacrifice == true
  4. unfinished_doll    - vars.humanity <= 0
  5. caught_and_confined - vars.suspicion_level >= 100
  6. eternal_dinner     - system.turn == turn_limit and flags.ending == null
"""
import pytest

from app.ending_checker import EndingChecker, check_ending
from app.schemas.game_state import NPCState, WorldStatePipeline
from app.schemas.status import NPCStatus
from app.loader import ScenarioAssets

from test.conftest import make_initial_world, make_stepmother, make_brother, make_dog_baron


@pytest.fixture
def checker():
    return EndingChecker()


# ============================================================
# 초기 상태: 엔딩 미도달
# ============================================================
class TestNoEnding:
    def test_initial_state_no_ending(self, checker, assets, initial_world):
        result = checker.check(initial_world, assets)
        assert result.reached is False
        assert result.ending is None

    def test_midgame_no_ending(self, checker, assets):
        world = make_initial_world(
            turn=15,
            vars={"humanity": 60, "suspicion_level": 40, "day": 2, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is False


# ============================================================
# 승리 엔딩 1: stealth_exit (완벽한 기만)
# ============================================================
class TestStealthExit:
    """condition: has_item(secret_key) and npc.stepmother.status == 'sleeping'"""

    def test_both_conditions_met(self, checker, assets):
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
        )
        world.npcs["stepmother"].stats["status"] = "sleeping"
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "stealth_exit"
        assert result.ending.name == "완벽한 기만 (The Stealth Exit)"
        assert "ending" in result.triggered_delta.flags

    def test_has_key_but_stepmother_alive(self, checker, assets):
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
        )
        # stepmother stats에 status 필드 없음 → 기본 "" → 'sleeping' 아님
        result = checker.check(world, assets)
        # 다른 엔딩 조건도 안 맞으면 미도달
        assert result.reached is False or result.ending.ending_id != "stealth_exit"

    def test_stepmother_sleeping_but_no_key(self, checker, assets):
        world = make_initial_world()
        world.npcs["stepmother"].stats["status"] = "sleeping"
        result = checker.check(world, assets)
        assert result.reached is False or result.ending.ending_id != "stealth_exit"

    def test_skip_has_item_skips_stealth_exit(self, checker, assets):
        """skip_has_item=True이면 has_item 포함 엔딩 건너뜀"""
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
        )
        world.npcs["stepmother"].stats["status"] = "sleeping"
        result = checker.check(world, assets, skip_has_item=True)
        # stealth_exit은 has_item을 포함하므로 스킵됨
        if result.reached:
            assert result.ending.ending_id != "stealth_exit"


# ============================================================
# 승리 엔딩 2: chaotic_breakout (혼돈의 밤)
# ============================================================
class TestChaoticBreakout:
    """condition: flags.house_on_fire == true"""

    def test_house_on_fire(self, checker, assets):
        world = make_initial_world(
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": True,
                   "house_on_fire": True},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "chaotic_breakout"
        assert result.ending.name == "혼돈의 밤 (The Chaotic Breakout)"

    def test_house_not_on_fire(self, checker, assets):
        world = make_initial_world(
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": True,
                   "house_on_fire": False},
        )
        result = checker.check(world, assets)
        assert result.reached is False or result.ending.ending_id != "chaotic_breakout"

    def test_oil_only_not_enough(self, checker, assets):
        """기름만 뿌리고 불을 안 붙인 상태"""
        world = make_initial_world(
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": True,
                   "house_on_fire": False},
        )
        result = checker.check(world, assets)
        if result.reached:
            assert result.ending.ending_id != "chaotic_breakout"

    def test_not_skipped_by_skip_has_item(self, checker, assets):
        """chaotic_breakout은 has_item이 없으므로 skip_has_item에 영향 없음"""
        world = make_initial_world(
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": True,
                   "house_on_fire": True},
        )
        result = checker.check(world, assets, skip_has_item=True)
        assert result.reached is True
        assert result.ending.ending_id == "chaotic_breakout"


# ============================================================
# 승리 엔딩 3: sibling_sacrifice (조력자의 희생)
# ============================================================
class TestSiblingSacrifice:
    """condition: has_item(secret_key) and flags.brother_sacrifice == true"""

    def test_both_conditions_met(self, checker, assets):
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
            flags={"ending": None, "brother_sacrifice": True,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "sibling_sacrifice"

    def test_has_key_but_no_sacrifice(self, checker, assets):
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
        )
        result = checker.check(world, assets)
        assert result.reached is False or result.ending.ending_id != "sibling_sacrifice"

    def test_sacrifice_but_no_key(self, checker, assets):
        world = make_initial_world(
            flags={"ending": None, "brother_sacrifice": True,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
        )
        result = checker.check(world, assets)
        assert result.reached is False or result.ending.ending_id != "sibling_sacrifice"


# ============================================================
# 패배 엔딩 1: unfinished_doll (불완전한 박제)
# ============================================================
class TestUnfinishedDoll:
    """condition: vars.humanity <= 0"""

    def test_humanity_zero(self, checker, assets):
        world = make_initial_world(
            vars={"humanity": 0, "suspicion_level": 0, "day": 3, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "unfinished_doll"
        assert result.ending.name == "불완전한 박제 (The Unfinished Doll)"

    def test_humanity_negative(self, checker, assets):
        world = make_initial_world(
            vars={"humanity": -10, "suspicion_level": 0, "day": 4, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "unfinished_doll"

    def test_humanity_one(self, checker, assets):
        """경계값: humanity=1이면 엔딩 아님"""
        world = make_initial_world(
            vars={"humanity": 1, "suspicion_level": 0, "day": 3, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is False or result.ending.ending_id != "unfinished_doll"

    def test_not_skipped_by_skip_has_item(self, checker, assets):
        world = make_initial_world(
            vars={"humanity": 0, "suspicion_level": 0, "day": 3, "status_effects": []},
        )
        result = checker.check(world, assets, skip_has_item=True)
        assert result.reached is True
        assert result.ending.ending_id == "unfinished_doll"


# ============================================================
# 패배 엔딩 2: caught_and_confined (감시의 올가미)
# ============================================================
class TestCaughtAndConfined:
    """condition: vars.suspicion_level >= 100"""

    def test_suspicion_100(self, checker, assets):
        world = make_initial_world(
            vars={"humanity": 50, "suspicion_level": 100, "day": 3, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "caught_and_confined"
        assert result.ending.name == "감시의 올가미 (The Watchful Snare)"

    def test_suspicion_over_100(self, checker, assets):
        world = make_initial_world(
            vars={"humanity": 50, "suspicion_level": 120, "day": 4, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "caught_and_confined"

    def test_suspicion_99(self, checker, assets):
        """경계값: suspicion=99이면 엔딩 아님"""
        world = make_initial_world(
            vars={"humanity": 50, "suspicion_level": 99, "day": 3, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is False or result.ending.ending_id != "caught_and_confined"

    def test_humanity_zero_and_suspicion_100_priority(self, checker, assets):
        """humanity=0이고 suspicion=100이면 YAML 순서상 unfinished_doll이 먼저"""
        world = make_initial_world(
            vars={"humanity": 0, "suspicion_level": 100, "day": 4, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "unfinished_doll"  # 우선순위 높음


# ============================================================
# 패배 엔딩 3: eternal_dinner (영원한 식사 시간)
# ============================================================
class TestEternalDinner:
    """condition: system.turn == turn_limit and flags.ending == null"""

    def test_turn_limit_reached(self, checker, assets):
        turn_limit = assets.get_turn_limit()
        world = make_initial_world(
            turn=turn_limit,
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
            vars={"humanity": 50, "suspicion_level": 30, "day": 5, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "eternal_dinner"
        assert result.ending.name == "영원한 식사 시간 (The Eternal Dinner)"

    def test_turn_limit_minus_one(self, checker, assets):
        """경계값: turn_limit - 1이면 엔딩 아님"""
        turn_limit = assets.get_turn_limit()
        world = make_initial_world(
            turn=turn_limit - 1,
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
            vars={"humanity": 50, "suspicion_level": 30, "day": 5, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is False

    def test_turn_limit_but_ending_already_set(self, checker, assets):
        """turn_limit 도달했지만 이미 다른 엔딩이 설정됨"""
        turn_limit = assets.get_turn_limit()
        world = make_initial_world(
            turn=turn_limit,
            flags={"ending": "stealth_exit", "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
            vars={"humanity": 50, "suspicion_level": 30, "day": 5, "status_effects": []},
        )
        result = checker.check(world, assets)
        # ending이 null이 아니므로 eternal_dinner 조건 불충족
        if result.reached:
            assert result.ending.ending_id != "eternal_dinner"

    def test_not_skipped_by_skip_has_item(self, checker, assets):
        turn_limit = assets.get_turn_limit()
        world = make_initial_world(
            turn=turn_limit,
            flags={"ending": None, "brother_sacrifice": False,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
            vars={"humanity": 50, "suspicion_level": 30, "day": 5, "status_effects": []},
        )
        result = checker.check(world, assets, skip_has_item=True)
        assert result.reached is True
        assert result.ending.ending_id == "eternal_dinner"


# ============================================================
# 엔딩 우선순위 (YAML 순서)
# ============================================================
class TestEndingPriority:
    """여러 엔딩 조건이 동시 충족 시 YAML 순서가 앞선 것이 선택됨"""

    def test_stealth_exit_over_sibling_sacrifice(self, checker, assets):
        """stealth_exit과 sibling_sacrifice 동시 충족 시 stealth_exit 우선"""
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
            flags={"ending": None, "brother_sacrifice": True,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
        )
        world.npcs["stepmother"].stats["status"] = "sleeping"
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "stealth_exit"  # YAML 순서 1번

    def test_unfinished_doll_over_caught_confined(self, checker, assets):
        """humanity=0 + suspicion=100 → unfinished_doll 우선"""
        world = make_initial_world(
            vars={"humanity": 0, "suspicion_level": 100, "day": 4, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        assert result.ending.ending_id == "unfinished_doll"  # YAML 순서 4번 < 5번


# ============================================================
# triggered_delta 검증
# ============================================================
class TestTriggeredDelta:
    def test_delta_has_ending_flag(self, checker, assets):
        world = make_initial_world(
            vars={"humanity": 0, "suspicion_level": 0, "day": 3, "status_effects": []},
        )
        result = checker.check(world, assets)
        assert result.reached is True
        # triggered_delta.flags에 ending 키가 자동 주입됨
        assert "ending" in result.triggered_delta.flags
        assert result.triggered_delta.flags["ending"] == "unfinished_doll"


# ============================================================
# 편의 함수
# ============================================================
class TestConvenienceFunction:
    def test_check_ending_wrapper(self, assets, initial_world):
        result = check_ending(initial_world, assets)
        assert result.reached is False

    def test_check_ending_with_skip(self, assets):
        world = make_initial_world(
            inventory=["warm_black_tea", "secret_key"],
        )
        world.npcs["stepmother"].stats["status"] = "sleeping"
        result = check_ending(world, assets, skip_has_item=True)
        if result.reached:
            assert result.ending.ending_id != "stealth_exit"
