"""
app/services/game.py
GameService - 낮 파이프라인 통합

DB(Games 모델) → WorldState 변환 → 파이프라인 실행 → DB 저장
파이프라인: LockManager → DayController → EndingChecker → NarrativeLayer
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict
from app.crud import game as crud_game
from app.redis_client import get_redis_client

from app.schemas.client_sync import GameClientSyncSchema
from app.schemas.world_meta_data import WorldDataSchema, LocksSchemaList
from app.schemas.npc_info import NpcCollectionSchema
from app.schemas.player_info import PlayerSchema
from app.schemas.player_info import PlayerSchema
from app.day_controller import get_day_controller
from app.loader import ScenarioLoader, ScenarioAssets
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db_models.game import Games
from app.db_models.scenario import Scenario
from app.crud import game as crud_game
from app.loader import ScenarioAssets
from app.schemas.game_state import NPCState, WorldStatePipeline, StateDelta
from app.schemas.request_response import StepResponseSchema, NightResponseResult
from app.schemas.tool import ToolResult
from app.schemas.night import NightResult
from app.lock_manager import get_lock_manager
from app.ending_checker import check_ending
from app.narrative import get_narrative_layer
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
import logging

logger=logging.getLogger(__name__)

# ============================================================
# Delta 적용 로직
# ============================================================

def _apply_delta(
    world_state: WorldStatePipeline,
    delta_dict: Dict[str, Any],
    assets: ScenarioAssets | None = None,
) -> WorldStatePipeline:
    """StateDelta를 WorldStatePipeline에 적용 (in-place 변경 후 반환)"""
    delta = StateDelta.from_dict(delta_dict)

    # 1. NPC stats (delta + clamp 0~100)
    for npc_id, stat_changes in delta.npc_stats.items():
        if npc_id in world_state.npcs:
            npc = world_state.npcs[npc_id]
            for stat_name, delta_value in stat_changes.items():
                old = npc.stats.get(stat_name, 0)
                if isinstance(old, (int, float)) and isinstance(delta_value, (int, float)):
                    npc.stats[stat_name] = max(0, min(100, old + delta_value))
                else:
                    npc.stats[stat_name] = delta_value

    # 2. Flags (덮어쓰기)
    world_state.flags.update(delta.flags)

    # 3. Inventory
    for item_id in delta.inventory_add:
        if item_id and item_id not in world_state.inventory:
            world_state.inventory.append(item_id)
    for item_id in delta.inventory_remove:
        if item_id in world_state.inventory:
            world_state.inventory.remove(item_id)

    # 4. Locks (덮어쓰기)
    world_state.locks.update(delta.locks)

    # 5. Vars (숫자는 delta 적용, 그 외 덮어쓰기 + schema 범위 적용)
    var_schema = {}
    if assets:
        var_schema = assets.get_state_schema().get("vars", {})

    for key, value in delta.vars.items():
        old = world_state.vars.get(key, 0)
        if isinstance(old, (int, float)) and isinstance(value, (int, float)):
            new_value = old + value
            if key in var_schema:
                min_val = var_schema[key].get("min", float("-inf"))
                max_val = var_schema[key].get("max", float("inf"))
                new_value = max(min_val, min(max_val, new_value))
            world_state.vars[key] = new_value
        else:
            world_state.vars[key] = value

    # 6. Turn
    if delta.turn_increment > 0:
        world_state.turn += delta.turn_increment

    # 7. Memory
    for npc_id, memory_data in delta.memory_updates.items():
        if npc_id in world_state.npcs:
            world_state.npcs[npc_id].memory.update(memory_data)

    return world_state


def _world_state_to_games(game: Games, world_state: WorldStatePipeline) -> None:
    # 1) World Meta Data (turn, flags, vars, locks)
    snapshot = game.world_meta_data or {}
    state_data = snapshot.get("state", {})
    state_data["turn"] = world_state.turn
    state_data["flags"] = world_state.flags or {}
    state_data["vars"] = world_state.vars or {}
    state_data["day_action_log"] = list(world_state.day_action_log)
    snapshot["state"] = state_data

    locks_wrapper = snapshot.get("locks", {})
    locks_list = locks_wrapper.get("locks", [])
    ws_locks = world_state.locks or {}
    if isinstance(locks_list, list) and ws_locks:
        for lock_item in locks_list:
            if not isinstance(lock_item, dict):
                continue
            info_id = lock_item.get("info_id")
            if info_id in ws_locks:
                lock_item["is_unlocked"] = ws_locks[info_id]
    locks_wrapper["locks"] = locks_list
    snapshot["locks"] = locks_wrapper

    game.world_meta_data = snapshot
    flag_modified(game, "world_meta_data")

    # 2) Player Data (inventory)
    player_data = game.player_data or {}
    player_data["inventory"] = list(world_state.inventory or [])
    game.player_data = player_data
    flag_modified(game, "player_data")

    # 3) NPC Data (stats, memory)
    npc_data = game.npc_data or {"npcs": []}
    npc_list = npc_data.get("npcs", [])
    if not isinstance(npc_list, list):
        npc_list = []

    npc_index = {}
    for npc in npc_list:
        if isinstance(npc, dict):
            npc_id = npc.get("npc_id")
            if npc_id:
                npc_index[npc_id] = npc

    for npc_id, npc_state in (world_state.npcs or {}).items():
        target = npc_index.get(npc_id)
        if target is None:
            target = {"npc_id": npc_id}
            npc_list.append(target)
            npc_index[npc_id] = target

        stats = getattr(npc_state, "stats", None)
        if stats is None and isinstance(npc_state, dict):
            stats = npc_state.get("stats")
        if stats is not None:
            target["stats"] = stats

        memory = getattr(npc_state, "memory", None)
        if memory is None and isinstance(npc_state, dict):
            memory = npc_state.get("memory")
        if memory is not None:
            target["memory"] = memory

    npc_data["npcs"] = npc_list
    game.npc_data = npc_data
    flag_modified(game, "npc_data")

# ============================================================
# 코랩 테스팅용 목업 데이터 생성 함수 (YAML 파일 기반)
# ============================================================

@staticmethod
def mock_load_scenario_assets_from_yaml(scenario_id: str = "coraline_v3") -> ScenarioAssets:
    """
    [TESTING] 실제 YAML 파일을 읽어서 ScenarioAssets 생성
    코랩에서 DB 없이 테스트할 때 사용

    Args:
        scenario_id: 로드할 시나리오 ID (기본값: "coraline")

    Returns:
        ScenarioAssets: 로드된 시나리오 에셋
    """
    project_root = Path(__file__).parent.parent.parent
    scenarios_dir = project_root / "scenarios"

    loader = ScenarioLoader(base_path=scenarios_dir)
    assets = loader.load(scenario_id)

    print(f"[MOCK] Loaded ScenarioAssets from YAML: {scenario_id}")
    print(f"  - NPCs: {len(assets.get_all_npc_ids())}")
    print(f"  - Items: {len(assets.get_all_item_ids())}")
    print(f"  - State Schema Vars: {list(assets.get_state_schema().get('vars', {}).keys())}")

    return assets

@staticmethod
def mock_create_world_state_from_yaml(scenario_id: str = "coraline_v3") -> WorldStatePipeline:
    """
    [TESTING] 실제 YAML 파일을 읽어서 초기 WorldState 생성
    코랩에서 DB 없이 테스트할 때 사용

    Args:
        scenario_id: 로드할 시나리오 ID (기본값: "coraline")

    Returns:
        WorldState: 초기화된 월드 상태
    """
    # 1. ScenarioAssets 로드
    project_root = Path(__file__).parent.parent.parent
    scenarios_dir = project_root / "scenarios"
    loader = ScenarioLoader(base_path=scenarios_dir)
    assets = loader.load(scenario_id)

    # 2. NPCState 생성 (YAML의 npcs 데이터 기반)
    npcs = {}
    for npc_dict in assets.npcs.get("npcs", []):
        npc_id = npc_dict.get("npc_id")
        if not npc_id:
            continue

        # stats 필드에서 초기 스탯 가져오기
        stats = npc_dict.get("stats", {})

        npcs[npc_id] = NPCState(
            npc_id=npc_id,
            stats=dict(stats),  # affection, fear, humanity 등
            memory={}  # 초기 메모리는 비어있음
        )

    # 3. 초기 인벤토리 (YAML items에서 acquire.method == "start"인 것들)
    initial_inventory = assets.get_initial_inventory()

    # 4. 초기 locks (모두 잠금 상태로 시작)
    locks = {}
    if "locks" in assets.extras:
        locks_data = assets.extras["locks"]
        if isinstance(locks_data, dict) and "locks" in locks_data:
            for lock in locks_data["locks"]:
                info_id = lock.get("info_id")
                if info_id:
                    locks[info_id] = lock.get("is_unlocked", False)

    # 5. 초기 vars (state_schema에서 default 값 가져오기)
    vars_data = {}
    state_schema = assets.get_state_schema()
    for var_name, var_config in state_schema.get("vars", {}).items():
        vars_data[var_name] = var_config.get("default", 0)

    # 6. 초기 flags (state_schema에서 default 값 가져오기)
    flags_data = {}
    for flag_name, flag_config in state_schema.get("flags", {}).items():
        flags_data[flag_name] = flag_config.get("default", None)

    world_state = WorldStatePipeline(
        turn=1,
        npcs=npcs,
        flags=flags_data,
        inventory=initial_inventory,
        locks=locks,
        vars=vars_data
    )

    print(f"[MOCK] Created WorldState from YAML: {scenario_id}")
    print(f"  - Turn: {world_state.turn}")
    print(f"  - NPCs: {list(world_state.npcs.keys())}")
    print(f"  - Initial Inventory: {world_state.inventory}")
    print(f"  - Vars: {world_state.vars}")
    print(f"  - Flags: {world_state.flags}")

    return world_state


class GameService:

    @staticmethod
    def _create_world_state(game: Games) -> WorldStatePipeline:
        """
        Game 모델에서 WorldStatePipeline 객체를 생성합니다.
        """
        # 1. World Meta Data (Turn, Flags, Vars, Locks)
        meta = game.world_meta_data or {}
        state_data = meta.get("state", {})
        
        turn = state_data.get("turn", 1)
        flags = state_data.get("flags", {})
        vars_ = state_data.get("vars", {})
        day_action_log = state_data.get("day_action_log", [])
        
        # Locks: list -> dict mapping
        locks_wrapper = meta.get("locks", {})
        locks_list = locks_wrapper.get("locks", [])
        locks = {
            l["info_id"]: l["is_unlocked"] 
            for l in locks_list 
            if "info_id" in l and "is_unlocked" in l
        }

        # 2. Player Data (Inventory)
        player = game.player_data or {}
        inventory = player.get("inventory", [])

        # 3. NPC Data (NPCState)
        target_npc_data = game.npc_data or {"npcs": []}
        npcs = {}
        for npc in target_npc_data.get("npcs", []):
            nid = npc.get("npc_id")
            if not nid:
                continue

            npcs[nid] = NPCState(
                npc_id=nid,
                stats=npc.get("stats", {}),
                memory=npc.get("memory", {}),
            )

        return WorldStatePipeline(
            turn=turn,
            npcs=npcs,
            flags=flags,
            inventory=inventory,
            locks=locks,
            vars=vars_,
            day_action_log=day_action_log,
        )

    @staticmethod
    def apply_chat_result(game: Games, result: ToolResult | dict) -> None:
        """
        DayController 실행 결과(ToolResult)를 DB 모델(game)에 반영합니다.
        
        Args:
            game: SQLAlchemy Games 인스턴스
            result: DayController 결과 (ToolResult 객체 또는 dict)
        """
        # ToolResult 객체면 dict로 변환 (기존 로직 호환성)
        if hasattr(result, "state_delta"):
            delta = result.state_delta
            memory_update = result.memory
        else:
            delta = result.get("state_delta", {})
            memory_update = result.get("memory", {})

        # (1) World Snapshot 업데이트
        snapshot = game.world_meta_data or {}
        
        # 1-1. State (Flags, Vars, Turn)
        state_data = snapshot.get("state", {})
        
        # [DEBUG] Turn Check Before
        print(f"[DEBUG] apply_chat_result - Before Turn: {state_data.get('turn')}, Increment: {delta.get('turn_increment')}")
        
        # Flags
        state_data.setdefault("flags", {}).update(delta.get("flags", {}))
        
        # Vars (단순 덮어쓰기 예시 - 실제로는 증감 로직 필요할 수 있음)
        vars_delta = delta.get("vars", {})
        current_vars = state_data.setdefault("vars", {})
        for k, v in vars_delta.items():
            current_vars[k] = v
            
        # Turn
        old_turn = state_data.get("turn", 1)
        increment = delta.get("turn_increment", 0)
        state_data["turn"] = old_turn + increment
        
        # [DEBUG] Turn Check After
        print(f"[DEBUG] apply_chat_result - After Turn: {state_data['turn']}")
        
        snapshot["state"] = state_data
        
        # 1-2. Locks
        locks_wrapper = snapshot.get("locks", {})
        locks_list = locks_wrapper.get("locks", [])
        locks_delta = delta.get("locks", {})
        
        if locks_delta:
            for lock_item in locks_list:
                lid = lock_item.get("info_id")
                if lid and lid in locks_delta:
                    lock_item["is_unlocked"] = locks_delta[lid]
        
        locks_wrapper["locks"] = locks_list
        snapshot["locks"] = locks_wrapper
        
        # 중요: 변경된 dict를 다시 할당 (SQLAlchemy JSONB 변경 감지)
        # 중요: 변경된 dict를 다시 할당 (SQLAlchemy JSONB 변경 감지)
        game.world_meta_data = snapshot
        flag_modified(game, "world_meta_data") # Explicitly flag as modified

        # (2) Player Data 업데이트
        p_data = game.player_data or {}
        
        # Inventory
        current_inv = set(p_data.get("inventory", []))
        for item in delta.get("inventory_add", []):
            current_inv.add(item)
        for item in delta.get("inventory_remove", []):
            if item in current_inv:
                current_inv.remove(item)
        p_data["inventory"] = list(current_inv)
        
        # Memory
        mem = p_data.get("memory", [])
        if memory_update:
            mem.append(memory_update)
        p_data["memory"] = mem
        
        game.player_data = p_data
        flag_modified(game, "player_data") # Explicitly flag as modified

        # (3) NPC Data 업데이트
        n_data = game.npc_data or {"npcs": []}
        npc_list = n_data.get("npcs", [])
        npc_stats_delta = delta.get("npc_stats", {})
        
        for npc in npc_list:
            nid = npc.get("npc_id")
            if nid and nid in npc_stats_delta:
                changes = npc_stats_delta[nid]
                if "stats" not in npc:
                    npc["stats"] = {}
                
                for stat_k, stat_v in changes.items():
                    current_val = npc["stats"].get(stat_k, 0)
                    npc["stats"][stat_k] = current_val + stat_v
                    
        n_data["npcs"] = npc_list
        game.npc_data = n_data
        flag_modified(game, "npc_data") # Explicitly flag as modified

    @classmethod
    def process_turn(
        cls,
        db: Session,
        game_id: int,
        input_data: Dict[str, Any],
        game: Games,
    ) -> StepResponseSchema:
        """
        낮 파이프라인 실행:
        LockManager → DayController → EndingChecker → NarrativeLayer → DB 저장
        """
        logger.info(f"process_turn: game_id={game_id}, input={input_data}")

        # ── Step 1: WorldStatePipeline 생성
        world_state = cls._create_world_state(game)

        # ── Step 2: Scenario Assets 로드
        assets = None
        if game.scenario and game.scenario.world_asset_data:
            try:
                # DB에 저장된 에셋 사용
                # world_asset_data는 dict 형태여야 함
                assets = ScenarioAssets(**game.scenario.world_asset_data)
                logger.info(f"Loaded assets from DB for scenario: {game.scenario.title}")
            except Exception as e:
                logger.warning(f"Failed to load assets from DB: {e}")

        if not assets:
            # Fallback: 파일 로드
            scenario_title = game.scenario.title if game.scenario else "coraline"
            project_root = Path(__file__).parent.parent.parent
            scenarios_dir = project_root / "scenarios"
            loader = ScenarioLoader(base_path=scenarios_dir)
            assets = loader.load(scenario_title)
            logger.info(f"Loaded assets from FILE for scenario: {scenario_title}")

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)

        # ── Step 3.5: StatusEffectManager - 만료 효과 해제 ──
        from app.status_effect_manager import get_status_effect_manager
        sem = get_status_effect_manager()
        sem.tick(world_state.turn, world_state)

        # ── Step 4: DayController - 낮 턴 실행 ──
        user_text = input_data.get("chat_input", "")
        day_controller = get_day_controller()
        tool_result: ToolResult = day_controller.process(
            user_text,
            world_state,
            assets,
        )
        
        logger.debug(f"DayController result: {tool_result}")

        # ── Step 5: Delta 적용 ──
        world_after = _apply_delta(world_state, tool_result.state_delta, assets)

        # ── Step 5.5: ItemAcquirer - 자동 아이템 획득 스캔 ──
        from app.item_acquirer import get_item_acquirer
        acquirer = get_item_acquirer()
        acq_result = acquirer.scan(world_after, assets)
        if acq_result.newly_acquired:
            world_after = _apply_delta(world_after, acq_result.acquisition_delta, assets)
            for acq_item_id in acq_result.newly_acquired:
                acq_item_def = assets.get_item_by_id(acq_item_id)
                acq_item_name = acq_item_def.get("name", acq_item_id) if acq_item_def else acq_item_id
                tool_result.event_description.append(f"'{acq_item_name}'을(를) 발견했다!")

        # ── Step 5.6: day_action_log 축적 (밤 가족회의 안건용) ──
        day_log_entry = {
            "turn": world_after.turn,
            "input": user_text,
            "intent": tool_result.intent,
            "events": tool_result.event_description,
        }
        world_after.day_action_log.append(day_log_entry)

        # ── Step 6: EndingChecker - 엔딩 체크 ──
        # 아이템 사용으로 엔딩이 트리거된 경우 (ItemUseResolver에서 판정)
        ending_info = tool_result.ending_info
        if not ending_info:
            # 패시브 엔딩 체크 (has_item 조건은 스킵 — 아이템 사용 시에만 트리거)
            ending_result = check_ending(world_after, assets, skip_has_item=True)
            ending_info = ending_result.to_ending_info_dict()
            if ending_result.reached:
                _apply_delta(world_after, ending_result.triggered_delta.to_dict(), assets)

        # ── Step 7: NarrativeLayer - 나레이션 생성 ──
        narrative_layer = get_narrative_layer()
        if ending_info:
            narrative = narrative_layer.render_ending(
                ending_info,
                world_after,
                assets,
            )
        else:
            narrative = narrative_layer.render(
                world_after,
                assets,
                event_description=tool_result.event_description,
                state_delta=tool_result.state_delta,
                npc_response=tool_result.npc_response,
            )

        # ── Step 8: WorldStatePipeline → DB 반영 ──
        _world_state_to_games(game, world_after)

        # ── Step 9: DB 저장 ──
        crud_game.update_game(db, game)

        logger.info(
            f"Day completed: game={game_id}, "
            f"turn={world_after.turn}, ending={ending_info is not None}"
        )

        return StepResponseSchema(
            narrative=narrative,
            ending_info=ending_info,
            world_state=world_after.to_dict(),
        )

    @classmethod
    def process_night(
        cls,
        db: Session,
        game_id: int,
        game: Games,
    ) -> NightResponseResult:
        """
        밤 파이프라인 실행:
        LockManager → NightController → Delta 적용 → EndingChecker → NarrativeLayer

        Args:
            db: SQLAlchemy 세션
            game_id: 게임 ID
            game: Games DB 인스턴스

        Returns:
            NightTurnResult: 밤 파이프라인 실행 결과
        """
        # ── Step 1: WorldState 생성
        world_state = cls._create_world_state(game)

        # ── Step 2: Scenario Assets 로드
        assets = None
        if game.scenario and game.scenario.world_asset_data:
            try:
                # DB에 저장된 에셋 사용
                # world_asset_data는 dict 형태여야 함
                assets = ScenarioAssets(**game.scenario.world_asset_data)
                logger.info(f"Loaded assets from DB for scenario: {game.scenario.title}")
            except Exception as e:
                logger.warning(f"Failed to load assets from DB: {e}")

        if not assets:
            # Fallback: 파일 로드
            scenario_title = game.scenario.title if game.scenario else "coraline"
            project_root = Path(__file__).parent.parent.parent
            scenarios_dir = project_root / "scenarios"
            loader = ScenarioLoader(base_path=scenarios_dir)
            assets = loader.load(scenario_title)
            logger.info(f"Loaded assets from FILE for scenario: {scenario_title}")

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)

        # ── Step 4: NightController - 밤 턴 실행 ──
        night_controller = get_night_controller()
        night_result: NightResult = night_controller.process(
            world_state, 
            assets
            )

        # ── Step 5: Delta 적용 ──
        world_after = _apply_delta(world_state, night_result.night_delta, assets)

        # ── Step 6: EndingChecker - 엔딩 체크 (has_item 조건 스킵) ──
        ending_result = check_ending(world_after, assets, skip_has_item=True)
        ending_info = ending_result.to_ending_info_dict()
        if ending_result.reached:
            _apply_delta(world_after, ending_result.triggered_delta.to_dict(), assets)

        # ── Step 7: NarrativeLayer - 나레이션 생성 ──
        narrative_layer = get_narrative_layer()
        if ending_info:
            narrative = narrative_layer.render_ending(
                ending_info,
                world_after,
                assets,
            )
        else:
            narrative = narrative_layer.render(
                world_after,
                assets,
                event_description=night_result.night_description,
                state_delta=night_result.night_delta,
                night_conversation=night_result.night_conversation,
            )

        # ── Step 7.5: day_action_log 초기화 (다음 낮을 위해) ──
        world_after.day_action_log = []

        # ── Step 8: WorldStatePipeline → DB 반영 ──
        _world_state_to_games(game, world_after)

        # ── Step 9: DB 저장 ──
        crud_game.update_game(db, game)

        logger.info(
            f"Night completed: game={game_id}, "
            f"turn={world_after.turn}, ending={ending_result.reached}"
        )

        return NightResponseResult(
            narrative=narrative,
            world_state=world_after.to_dict(),
            ending_info=ending_info,
        )

    @staticmethod
    def start_game(db: Session, game_id: int):
        """게임 id를 받아서 진행된 게임을 불러옴"""
        from app.schemas import GameClientSyncSchema, WorldDataSchema, PlayerSchema, NpcCollectionSchema
        from app.redis_client import get_redis_client

        game = crud_game.get_game_by_id(db, game_id)
        if not game:
            raise ValueError(f"Game not found: {game_id}")

        # 0. NPC Long-term Plan 초기화 (최초 1회)
        GameService._initialize_npc_plans(db, game)

        # 1. World Data
        # snapshot은 이미 WorldDataSchema 구조(dict)로 저장되어 있다고 가정
        # 만약 타입 불일치가 걱정된다면 **unpacking으로 안전하게 생성
        world_obj = WorldDataSchema(**(game.world_meta_data or {}))

        # 2. Player Data
        # DB에 저장된 player_data를 PlayerSchema로 변환
        player_obj = PlayerSchema(**(game.player_data or {}))
        npc_data = copy.deepcopy(game.npc_data) or {"npcs": []}
        npcs_obj = NpcCollectionSchema(**npc_data)

        client_sync_data = GameClientSyncSchema(
            world=world_obj,
            player=player_obj,
            npcs=npcs_obj,
        )

        try:
            redis_client = get_redis_client()
            redis_key = f"game:{game_id}"
            redis_client.setex(redis_key, 3600, client_sync_data.json())
        except Exception as e:
            logger.warning(f"Failed to cache game state in Redis: {e}")

        return client_sync_data

    @classmethod
    def _initialize_npc_plans(cls, db: Session, game: Games) -> None:
        """게임 최초 시작 시 모든 NPC의 Long-term Plan을 생성.

        이미 LT plan이 있으면 스킵한다.
        """
        from app.agents.planning import generate_long_term_plan
        from app.llm import get_llm

        world_state = cls._create_world_state(game)

        # Assets 로드
        assets = None
        if game.scenario and game.scenario.world_asset_data:
            try:
                assets = ScenarioAssets(**game.scenario.world_asset_data)
            except Exception:
                pass
        if not assets:
            scenario_title = game.scenario.title if game.scenario else "coraline"
            project_root = Path(__file__).parent.parent.parent
            scenarios_dir = project_root / "scenarios"
            loader = ScenarioLoader(base_path=scenarios_dir)
            assets = loader.load(scenario_title)

        # LT plan이 하나라도 이미 있으면 스킵
        any_has_plan = any(
            npc_state.memory.get("long_term_plan")
            for npc_state in world_state.npcs.values()
        )
        if any_has_plan:
            return

        llm = get_llm()
        scenario_title = assets.scenario.get("title", "")
        changed = False

        for npc_id, npc_state in world_state.npcs.items():
            npc_data = assets.get_npc_by_id(npc_id)
            if not npc_data:
                continue

            npc_goal = npc_data.get("goal", "")
            phases = npc_data.get("phases", [])
            if not npc_goal or not phases:
                continue

            lt_plan = generate_long_term_plan(
                npc_id=npc_id,
                npc_name=npc_data["name"],
                persona=npc_data.get("persona", {}),
                npc_goal=npc_goal,
                initial_phase=phases[0],
                stats=npc_state.stats,
                scenario_title=scenario_title,
                llm=llm,
            )
            npc_state.memory["long_term_plan"] = lt_plan
            npc_state.memory["current_phase_id"] = phases[0].get("phase_id", "A")
            npc_state.memory["last_reflected_phase_id"] = phases[0].get("phase_id", "A")
            changed = True
            logger.info(f"[GameService] LT plan generated for {npc_id}: {lt_plan[:60]}...")

        if changed:
            _world_state_to_games(game, world_state)
            crud_game.update_game(db, game)
            logger.info("[GameService] NPC LT plans saved to DB")
