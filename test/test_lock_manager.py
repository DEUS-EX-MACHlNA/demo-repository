"""
test/test_lock_manager.py
LockManager 전체 분기 테스트

locks.yaml의 모든 lock에 대해:
  - unlock_condition 충족/미충족 시 동작
  - 중복 해금 방지
  - NPC 메모리 주입
  - allowed_npcs 접근 제어

Lock 목록:
  quest_gate:
    quest_escape_route     - npc.brother.affection >= 70
    quest_fire_weakness    - npc.grandmother.affection >= 50
    quest_brother_sacrifice - flags.brother_sacrifice == true
  item_hint:
    hint_sedative          - locks.quest_blood_request == true  (주의: quest_blood_request는 현재 미정의)
    hint_oil_bottle        - npc.grandmother.humanity >= 40
    hint_dried_herbs       - vars.day >= 2
  npc_topic:
    topic_brother_injury   - npc.brother.affection >= 60
    topic_father_regret    - npc.stepfather.humanity >= 40 and has_item(real_family_photo)
  lore:
    lore_surgery_log       - vars.humanity <= 60 and vars.suspicion_level >= 30
    lore_mothers_true_form - npc.grandmother.humanity >= 30
    lore_decay_scent       - npc.dog_baron.affection >= 80
    lore_serial_number     - vars.humanity <= 30 or vars.day >= 4
    lore_mirage_gateway    - locks.lore_surgery_log == true and locks.lore_serial_number == true
"""
import pytest
from unittest.mock import patch, MagicMock

from app.lock_manager import LockManager
from app.schemas.game_state import NPCState, WorldStatePipeline

from test.conftest import (
    make_initial_world, make_stepmother, make_stepfather,
    make_brother, make_grandmother, make_dog_baron,
)


@pytest.fixture
def manager():
    return LockManager()


# 메모리 주입을 모킹하여 외부 의존성 제거
@pytest.fixture(autouse=True)
def mock_memory_injection():
    with patch("app.lock_manager.LockManager._inject_to_npc_memory", return_value=[]):
        yield


# ============================================================
# 초기 상태: 아무것도 해금 안됨
# ============================================================
class TestInitialState:
    def test_no_unlocks_on_initial(self, manager, locks_data, initial_world):
        result = manager.check_unlocks(initial_world, locks_data)
        # 초기에 조건 충족 가능한 lock이 없어야 함
        # (hint_dried_herbs는 day>=2인데 초기 day=1)
        unlocked_ids = {info.info_id for info in result.newly_unlocked}
        # quest_escape_route: brother.affection >= 70 → 50 → X
        # quest_fire_weakness: grandmother.affection >= 50 → 20 → X
        assert "quest_escape_route" not in unlocked_ids
        assert "quest_fire_weakness" not in unlocked_ids


# ============================================================
# quest_gate: quest_escape_route
# ============================================================
class TestQuestEscapeRoute:
    """unlock_condition: npc.brother.affection >= 70"""

    def test_brother_affection_70(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=70),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "quest_escape_route" in ids

    def test_brother_affection_69(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=69),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "quest_escape_route" not in ids

    def test_allowed_npcs_is_brother(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=80),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        for info in result.newly_unlocked:
            if info.info_id == "quest_escape_route":
                assert "brother" in info.allowed_npcs


# ============================================================
# quest_gate: quest_fire_weakness
# ============================================================
class TestQuestFireWeakness:
    """unlock_condition: npc.grandmother.affection >= 50"""

    def test_grandmother_affection_50(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(),
                "grandmother": make_grandmother(affection=50),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "quest_fire_weakness" in ids

    def test_grandmother_affection_49(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(),
                "grandmother": make_grandmother(affection=49),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "quest_fire_weakness" not in ids


# ============================================================
# quest_gate: quest_brother_sacrifice
# ============================================================
class TestQuestBrotherSacrifice:
    """unlock_condition: flags.brother_sacrifice == true"""

    def test_sacrifice_flag_true(self, manager, locks_data):
        world = make_initial_world(
            flags={"ending": None, "brother_sacrifice": True,
                   "stepmother_away": False, "oil_on_stepmother": False,
                   "house_on_fire": False},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "quest_brother_sacrifice" in ids

    def test_sacrifice_flag_false(self, manager, locks_data):
        world = make_initial_world()
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "quest_brother_sacrifice" not in ids


# ============================================================
# item_hint: hint_oil_bottle
# ============================================================
class TestHintOilBottle:
    """unlock_condition: npc.grandmother.humanity >= 40"""

    def test_grandmother_humanity_40(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(),
                "grandmother": make_grandmother(humanity=40),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "hint_oil_bottle" in ids

    def test_grandmother_humanity_10(self, manager, locks_data, initial_world):
        """초기 humanity=10 → 미해금"""
        result = manager.check_unlocks(initial_world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "hint_oil_bottle" not in ids


# ============================================================
# item_hint: hint_dried_herbs
# ============================================================
class TestHintDriedHerbs:
    """unlock_condition: vars.day >= 2"""

    def test_day_2(self, manager, locks_data):
        world = make_initial_world(
            vars={"humanity": 100, "suspicion_level": 0, "day": 2, "status_effects": []},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "hint_dried_herbs" in ids

    def test_day_1(self, manager, locks_data, initial_world):
        result = manager.check_unlocks(initial_world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "hint_dried_herbs" not in ids


# ============================================================
# npc_topic: topic_brother_injury
# ============================================================
class TestTopicBrotherInjury:
    """unlock_condition: npc.brother.affection >= 60"""

    def test_affection_60(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=60),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "topic_brother_injury" in ids

    def test_affection_59(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=59),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "topic_brother_injury" not in ids


# ============================================================
# npc_topic: topic_father_regret
# ============================================================
class TestTopicFatherRegret:
    """unlock_condition: npc.stepfather.humanity >= 40 and has_item(real_family_photo)"""

    def test_both_conditions(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(humanity=40),
                "brother": make_brother(),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
            inventory=["warm_black_tea", "real_family_photo"],
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "topic_father_regret" in ids

    def test_humanity_but_no_photo(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(humanity=40),
                "brother": make_brother(),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "topic_father_regret" not in ids

    def test_photo_but_low_humanity(self, manager, locks_data):
        world = make_initial_world(
            inventory=["warm_black_tea", "real_family_photo"],
        )
        # stepfather.humanity == 20 (초기)
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "topic_father_regret" not in ids


# ============================================================
# lore: lore_surgery_log
# ============================================================
class TestLoreSurgeryLog:
    """unlock_condition: vars.humanity <= 60 and vars.suspicion_level >= 30"""

    def test_both_conditions(self, manager, locks_data):
        world = make_initial_world(
            vars={"humanity": 60, "suspicion_level": 30, "day": 3, "status_effects": []},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_surgery_log" in ids

    def test_humanity_61(self, manager, locks_data):
        world = make_initial_world(
            vars={"humanity": 61, "suspicion_level": 30, "day": 3, "status_effects": []},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_surgery_log" not in ids

    def test_suspicion_29(self, manager, locks_data):
        world = make_initial_world(
            vars={"humanity": 60, "suspicion_level": 29, "day": 3, "status_effects": []},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_surgery_log" not in ids


# ============================================================
# lore: lore_mothers_true_form
# ============================================================
class TestLoreMothersTrueForm:
    """unlock_condition: npc.grandmother.humanity >= 30"""

    def test_grandmother_humanity_30(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(),
                "grandmother": make_grandmother(humanity=30),
                "dog_baron": make_dog_baron(),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_mothers_true_form" in ids

    def test_grandmother_humanity_initial(self, manager, locks_data, initial_world):
        """초기 humanity=10 → 미해금"""
        result = manager.check_unlocks(initial_world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_mothers_true_form" not in ids


# ============================================================
# lore: lore_decay_scent
# ============================================================
class TestLoreDecayScent:
    """unlock_condition: npc.dog_baron.affection >= 80"""

    def test_affection_80(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(affection=80),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_decay_scent" in ids

    def test_affection_79(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(affection=79),
            },
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_decay_scent" not in ids


# ============================================================
# lore: lore_serial_number (OR 조건)
# ============================================================
class TestLoreSerialNumber:
    """unlock_condition: vars.humanity <= 30 or vars.day >= 4"""

    def test_humanity_30(self, manager, locks_data):
        world = make_initial_world(
            vars={"humanity": 30, "suspicion_level": 0, "day": 1, "status_effects": []},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_serial_number" in ids

    def test_day_4(self, manager, locks_data):
        world = make_initial_world(
            vars={"humanity": 100, "suspicion_level": 0, "day": 4, "status_effects": []},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_serial_number" in ids

    def test_neither_condition(self, manager, locks_data):
        world = make_initial_world(
            vars={"humanity": 50, "suspicion_level": 0, "day": 3, "status_effects": []},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_serial_number" not in ids


# ============================================================
# lore: lore_mirage_gateway (체인 해금)
# ============================================================
class TestLoreMirageGateway:
    """unlock_condition: locks.lore_surgery_log == true and locks.lore_serial_number == true"""

    def test_both_locks_unlocked(self, manager, locks_data):
        world = make_initial_world(
            locks={"lore_surgery_log": True, "lore_serial_number": True},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_mirage_gateway" in ids

    def test_only_surgery_log(self, manager, locks_data):
        world = make_initial_world(
            locks={"lore_surgery_log": True},
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_mirage_gateway" not in ids

    def test_neither_lock(self, manager, locks_data, initial_world):
        result = manager.check_unlocks(initial_world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "lore_mirage_gateway" not in ids


# ============================================================
# 중복 해금 방지
# ============================================================
class TestDuplicatePrevention:
    def test_already_unlocked_not_repeated(self, manager, locks_data):
        """world_state.locks에 이미 True로 설정된 lock은 다시 해금 안됨"""
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=80),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
            locks={"quest_escape_route": True},  # 이미 해금
        )
        result = manager.check_unlocks(world, locks_data)
        ids = {info.info_id for info in result.newly_unlocked}
        assert "quest_escape_route" not in ids  # 새로 해금된 것에 포함 안됨

    def test_second_check_no_duplicate(self, manager, locks_data):
        """같은 상태로 두 번 체크하면 두 번째는 빈 결과"""
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=80),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        result1 = manager.check_unlocks(world, locks_data)
        result2 = manager.check_unlocks(world, locks_data)

        first_ids = {info.info_id for info in result1.newly_unlocked}
        second_ids = {info.info_id for info in result2.newly_unlocked}

        # 첫 번째에서 해금된 것은 두 번째에서 안 나옴
        assert first_ids & second_ids == set()


# ============================================================
# 유틸리티 메서드
# ============================================================
class TestUtilityMethods:
    def test_is_unlocked(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=80),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        manager.check_unlocks(world, locks_data)
        assert manager.is_unlocked("quest_escape_route") is True
        assert manager.is_unlocked("quest_fire_weakness") is False

    def test_reset(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=80),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        manager.check_unlocks(world, locks_data)
        assert len(manager.get_all_unlocked_ids()) > 0

        manager.reset()
        assert len(manager.get_all_unlocked_ids()) == 0

    def test_get_unlocked_info_for_npc(self, manager, locks_data):
        world = make_initial_world(
            npcs={
                "stepmother": make_stepmother(),
                "stepfather": make_stepfather(),
                "brother": make_brother(affection=80),
                "grandmother": make_grandmother(),
                "dog_baron": make_dog_baron(),
            },
        )
        manager.check_unlocks(world, locks_data)

        brother_info = manager.get_unlocked_info_for_npc("brother", locks_data)
        brother_ids = {info.info_id for info in brother_info}
        assert "quest_escape_route" in brother_ids

        stepmother_info = manager.get_unlocked_info_for_npc("stepmother", locks_data)
        stepmother_ids = {info.info_id for info in stepmother_info}
        assert "quest_escape_route" not in stepmother_ids
