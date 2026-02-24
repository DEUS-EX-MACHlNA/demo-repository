"""
test/conftest.py
공용 테스트 픽스처 — 모든 테스트에서 공유

시나리오: 인형의 집 (coraline_v3)
NPC 초기 스탯:
  stepmother  - affection:50, humanity:100
  stepfather  - affection:30, humanity:20
  brother     - affection:50, humanity:50
  grandmother - affection:20, humanity:10
  dog_baron   - affection:70, humanity:100
"""
import copy
from pathlib import Path

import pytest

from app.schemas.game_state import NPCState, WorldStatePipeline, StateDelta
from app.schemas.status import NPCStatus
from app.loader import ScenarioLoader, ScenarioAssets


# ============================================================
# 시나리오 에셋 픽스처 (실제 YAML 로드)
# ============================================================

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"
SCENARIO_ID = "coraline_v3"


@pytest.fixture(scope="session")
def assets() -> ScenarioAssets:
    """coraline_v3 시나리오 에셋 (세션 범위 — 한 번만 로드)"""
    loader = ScenarioLoader(base_path=SCENARIOS_DIR)
    return loader.load(SCENARIO_ID)


@pytest.fixture(scope="session")
def locks_data(assets: ScenarioAssets) -> dict:
    """locks.yaml 원본 데이터"""
    return assets.extras.get("locks", {})


# ============================================================
# NPC 초기 상태 팩토리
# ============================================================

def _make_npc(npc_id: str, affection: int, humanity: int, **extra_stats) -> NPCState:
    stats = {"affection": affection, "humanity": humanity, "plus_hits": 0, "minus_hits": 0}
    stats.update(extra_stats)
    return NPCState(npc_id=npc_id, stats=stats, memory={})


def make_stepmother(affection=50, humanity=100, status=NPCStatus.ALIVE, **kw) -> NPCState:
    npc = _make_npc("stepmother", affection, humanity, **kw)
    npc.status = status
    return npc


def make_stepfather(affection=30, humanity=20, status=NPCStatus.ALIVE, **kw) -> NPCState:
    npc = _make_npc("stepfather", affection, humanity, **kw)
    npc.status = status
    return npc


def make_brother(affection=50, humanity=50, status=NPCStatus.ALIVE, **kw) -> NPCState:
    npc = _make_npc("brother", affection, humanity, **kw)
    npc.status = status
    return npc


def make_grandmother(affection=20, humanity=10, status=NPCStatus.ALIVE, **kw) -> NPCState:
    npc = _make_npc("grandmother", affection, humanity, **kw)
    npc.status = status
    return npc


def make_dog_baron(affection=70, humanity=100, status=NPCStatus.ALIVE, **kw) -> NPCState:
    npc = _make_npc("dog_baron", affection, humanity, **kw)
    npc.status = status
    return npc


# ============================================================
# WorldStatePipeline 팩토리
# ============================================================

def make_initial_world(**overrides) -> WorldStatePipeline:
    """게임 시작 시점의 초기 WorldState 생성"""
    defaults = dict(
        turn=1,
        npcs={
            "stepmother": make_stepmother(),
            "stepfather": make_stepfather(),
            "brother": make_brother(),
            "grandmother": make_grandmother(),
            "dog_baron": make_dog_baron(),
        },
        flags={
            "ending": None,
            "brother_sacrifice": False,
            "stepmother_away": False,
            "oil_on_stepmother": False,
            "house_on_fire": False,
        },
        inventory=["warm_black_tea"],
        locks={},
        vars={
            "humanity": 100,
            "suspicion_level": 0,
            "day": 1,
            "status_effects": [],
        },
    )
    defaults.update(overrides)

    # NPC는 deep copy 필요
    if "npcs" not in overrides:
        defaults["npcs"] = {k: v.model_copy(deep=True) for k, v in defaults["npcs"].items()}

    return WorldStatePipeline(**defaults)


@pytest.fixture
def initial_world() -> WorldStatePipeline:
    """초기 WorldState 픽스처"""
    return make_initial_world()


# ============================================================
# 사전 구성된 엔딩 직전 상태 픽스처
# ============================================================

@pytest.fixture
def world_near_stealth_exit() -> WorldStatePipeline:
    """stealth_exit 엔딩 직전 상태: secret_key 보유 + stepmother sleeping"""
    return make_initial_world(
        turn=20,
        npcs={
            "stepmother": make_stepmother(status=NPCStatus.SLEEPING),
            "stepfather": make_stepfather(status=NPCStatus.SLEEPING),
            "brother": make_brother(affection=80, status=NPCStatus.SLEEPING),
            "grandmother": make_grandmother(affection=30),
            "dog_baron": make_dog_baron(affection=95),
        },
        inventory=["warm_black_tea", "industrial_sedative", "secret_key"],
        vars={"humanity": 60, "suspicion_level": 20, "day": 3, "status_effects": []},
    )


@pytest.fixture
def world_near_chaotic_breakout() -> WorldStatePipeline:
    """chaotic_breakout 엔딩 직전 상태: oil_on_stepmother=true, 라이터 보유"""
    return make_initial_world(
        turn=18,
        npcs={
            "stepmother": make_stepmother(affection=10),
            "stepfather": make_stepfather(),
            "brother": make_brother(),
            "grandmother": make_grandmother(affection=60),
            "dog_baron": make_dog_baron(),
        },
        inventory=["warm_black_tea", "lighter", "oil_bottle"],
        flags={
            "ending": None,
            "brother_sacrifice": False,
            "stepmother_away": False,
            "oil_on_stepmother": True,
            "house_on_fire": False,
        },
        locks={"quest_fire_weakness": True},
        vars={"humanity": 50, "suspicion_level": 40, "day": 3, "status_effects": []},
    )


@pytest.fixture
def world_near_sibling_sacrifice() -> WorldStatePipeline:
    """sibling_sacrifice 엔딩 직전 상태: brother_sacrifice=true, secret_key 보유"""
    return make_initial_world(
        turn=22,
        npcs={
            "stepmother": make_stepmother(),
            "stepfather": make_stepfather(),
            "brother": make_brother(affection=85, humanity=80),
            "grandmother": make_grandmother(affection=30),
            "dog_baron": make_dog_baron(affection=95),
        },
        inventory=["warm_black_tea", "real_family_photo", "secret_key"],
        flags={
            "ending": None,
            "brother_sacrifice": True,
            "stepmother_away": False,
            "oil_on_stepmother": False,
            "house_on_fire": False,
        },
        locks={"quest_escape_route": True, "quest_brother_sacrifice": True},
        vars={"humanity": 70, "suspicion_level": 15, "day": 3, "status_effects": []},
    )


@pytest.fixture
def world_near_unfinished_doll() -> WorldStatePipeline:
    """unfinished_doll 엔딩 직전 상태: humanity 매우 낮음"""
    return make_initial_world(
        turn=30,
        vars={"humanity": 5, "suspicion_level": 50, "day": 4, "status_effects": []},
    )


@pytest.fixture
def world_near_caught_confined() -> WorldStatePipeline:
    """caught_and_confined 엔딩 직전 상태: suspicion_level 매우 높음"""
    return make_initial_world(
        turn=25,
        vars={"humanity": 40, "suspicion_level": 95, "day": 3, "status_effects": []},
    )


@pytest.fixture
def world_near_eternal_dinner(assets) -> WorldStatePipeline:
    """eternal_dinner 엔딩 직전 상태: turn == turn_limit - 1"""
    turn_limit = assets.get_turn_limit()
    return make_initial_world(
        turn=turn_limit - 1,
        flags={"ending": None, "brother_sacrifice": False,
               "stepmother_away": False, "oil_on_stepmother": False,
               "house_on_fire": False},
        vars={"humanity": 50, "suspicion_level": 30, "day": 5, "status_effects": []},
    )
