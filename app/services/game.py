"""
app/services/game.py
GameService - 낮 파이프라인 통합

DB(Games 모델) → WorldStatePipeline 변환 → 파이프라인 실행 → DB 저장
파이프라인: LockManager → DayController → EndingChecker → NarrativeLayer
"""

import copy
import logging
from typing import Any, Dict
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db_models.game import Games
from app.db_models.scenario import Scenario
from app.crud import game as crud_game
from app.redis_client import get_redis_client

from app.schemas.client_sync import GameClientSyncSchema
from app.schemas.world_meta_data import WorldDataSchema, LocksSchemaList
from app.schemas.npc_info import NpcCollectionSchema
from app.schemas.player_info import PlayerSchema
from app.schemas.item_info import ItemSchema
from app.schemas.request_response import StepRequestSchema, StepResponseSchema, NightResponseResult
from app.schemas.status import ItemStatus, LogType
from app.schemas.game_state import NPCState, WorldStatePipeline, StateDelta
from app.schemas.tool import ToolResult
from app.schemas.night import NightResult
from app.lock_manager import get_lock_manager
from app.ending_checker import check_ending
from app.narrative import get_narrative_layer
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
import logging

logger=logging.getLogger(__name__)

from app.crud.chat_log import create_chat_log
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
from app.loader import ScenarioLoader, ScenarioAssets
from app.lock_manager import get_lock_manager
from app.ending_checker import check_ending
from app.narrative import get_narrative_layer

from app.lock_manager import get_lock_manager
from app.ending_checker import check_ending
from app.narrative import get_narrative_layer
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
import logging

logger=logging.getLogger(__name__)

def _scenario_to_assets(game: Games) -> ScenarioAssets:
    assets = None
    if game.scenario and game.scenario.world_asset_data:
        try:
            # DB에 저장된 에셋 사용
            # world_asset_data는 dict 형태여야 함
            assets = ScenarioAssets(**game.scenario.world_asset_data)
            print(f"[GameService] Loaded assets from DB for scenario: {game.scenario.title}")
        except Exception as e:
            print(f"[GameService] Failed to load assets from DB: {e}")

    if not assets:
        # Fallback: 파일 로드
        scenario_title = game.scenario.title if game.scenario else "coraline"
        project_root = Path(__file__).parent.parent.parent
        scenarios_dir = project_root / "scenarios"
        loader = ScenarioLoader(base_path=scenarios_dir)
        assets = loader.load(scenario_title)
        print(f"[GameService] Loaded assets from FILE for scenario: {scenario_title}")

    # 3. Apply Persisted Item States
    if game.player_data and "item_states" in game.player_data:
        saved_states = game.player_data["item_states"]
        items_list = assets.items.get("items", [])
        for item in items_list:
            iid = item.get("item_id")
            if iid and iid in saved_states:
                item["state"] = saved_states[iid]

    return assets

# ============================================================
# Delta 적용 로직
# ============================================================

# TODO 이 부분은 나중에 덮어 쓰기 말고 계산하기도 적용될 예정
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

class GameService:

    """
    Game 모델에서 WorldStatePipeline 객체를 생성합니다.
    """
    @staticmethod
    def _create_world_state(game: Games) -> WorldStatePipeline:
        # 1. World Meta Data (Turn, Flags, Vars, Locks)
        meta = game.world_meta_data or {}
        state_data = meta.get("state", {})
    
        turn = state_data.get("turn", 1)
        date = state_data.get("date", 1)
        flags = state_data.get("flags", {})
        vars_ = state_data.get("vars", {})
        
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
        
        # 3. NPC Data
        npcs = {}
        if game.npc_data and "npcs" in game.npc_data:
            for npc_info in game.npc_data["npcs"]:
                nid = npc_info.get("npc_id")
                if nid:
                    npcs[nid] = NPCState.from_dict(npc_info)

        return WorldStatePipeline(
            turn=turn,
            date=date,
            npcs=npcs,
            flags=flags,
            inventory=player.get("inventory", []),
            locks=locks,
            vars=vars_
        )

    """
    WorldStatePipeline 객체를 Games DB 모델에 반영합니다.
    """
    @staticmethod
    def _world_state_to_games(game: Games, world_state: WorldStatePipeline, assets: ScenarioAssets | None = None) -> None:
        # 1. World Meta Data
        meta = game.world_meta_data or {}
        
        # 1-1. State (Turn, Date, Flags, Vars)
        state_data = meta.get("state", {})
        state_data["turn"] = world_state.turn
        state_data["date"] = world_state.date
        state_data["flags"] = world_state.flags
        state_data["vars"] = world_state.vars
        meta["state"] = state_data
        
        # 1-2. Locks
        # 기존 locks 구조 유지하면서 is_unlocked만 업데이트
        locks_wrapper = meta.get("locks", {})
        locks_list = locks_wrapper.get("locks", [])
        
        # world_state.locks는 {info_id: bool} 형태
        for lock_item in locks_list:
            info_id = lock_item.get("info_id")
            if info_id and info_id in world_state.locks:
                lock_item["is_unlocked"] = world_state.locks[info_id]
        
        locks_wrapper["locks"] = locks_list
        meta["locks"] = locks_wrapper
        
        game.world_meta_data = meta
        flag_modified(game, "world_meta_data")

        # 2. Player Data (Inventory)
        player = game.player_data or {}
        player["inventory"] = world_state.inventory

        # 2-1. Update Item Status in World Meta Data
        items_collection = meta.get("items", {})
        if items_collection:
            items_list = items_collection.get("items", [])
            for item in items_list:
                iid = item.get("item_id")
                if not iid:
                    continue
                if iid in world_state.inventory:
                    item["state"] = ItemStatus.ACQUIRED.value
                else:
                    current_state = item.get("state")
                    if current_state == ItemStatus.ACQUIRED.value:
                        item["state"] = ItemStatus.USED.value
            items_collection["items"] = items_list
            meta["items"] = items_collection
        
        game.player_data = player
        flag_modified(game, "player_data")

        # 3. NPC Data (Stats, Memory)
        npc_data = game.npc_data or {"npcs": []}
        npc_list = npc_data.get("npcs", [])
        
        for npc_dict in npc_list:
            npc_id = npc_dict.get("npc_id")
            if npc_id and npc_id in world_state.npcs:
                npc_state = world_state.npcs[npc_id]
                
                # Stats 업데이트
                npc_dict["stats"] = npc_state.stats
                
                # Memory 업데이트
                # 기존 memory가 있으면 병합하거나 덮어쓰기. 여기서는 덮어쓰기/병합
                # NPCState.memory는 dict 형태임
                current_mem = npc_dict.get("memory", {})
                if isinstance(current_mem, list): # 구버전 데이터 호환
                     current_mem = {}
                
                current_mem.update(npc_state.memory)
                npc_dict["memory"] = current_mem
        
        npc_data["npcs"] = npc_list
        game.npc_data = npc_data
        flag_modified(game, "npc_data")

    # ============================================================
    # 코랩 테스팅용 목업 데이터 생성 함수 (YAML 파일 기반)
    # ============================================================

    @staticmethod
    def mock_load_scenario_assets_from_yaml(scenario_id: str = "coraline") -> ScenarioAssets:
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
    def mock_create_world_state_from_yaml(scenario_id: str = "coraline") -> WorldStatePipeline:
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

    @classmethod
    def process_turn(
        cls,
        db: Session,
        game_id: int,
        input_data: StepRequestSchema,
        game: Games,
    ) -> StepResponseSchema:
        """
        낮 파이프라인 실행:
        LockManager → DayController → EndingChecker → NarrativeLayer → DB 저장
        """
        
        
        debug: Dict[str, Any] = {"game_id": game_id, "steps": []}

        # ── Step 1: world state 생성 ──
        world_state = cls._create_world_state(game)

        # ── Step 2: Scenario Assets 로드 ──
        assets = _scenario_to_assets(game)

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)

        # ── Step 4: DayController - 낮 턴 실행 ──
        user_input = input_data.to_combined_string()
        day_controller = get_day_controller()
        tool_result: ToolResult = day_controller.process(
            user_input,
            world_state,
            assets,
        )
        debug["steps"].append({
            "step": "day_turn",
            "state_delta": tool_result.state_delta,
        })

        # [TESTING] Mock Data Preservation (User Request)
        # 이 변수는 테스팅 목적이나 Fallback으로 사용될 수 있습니다.
        # ToolResult 객체로 변환하여 보존
        
        
        #tool_result = make_mock_tool_result(user_input)

        
        logger.debug(f"DayController result: {tool_result}")

        # ── Step 5: Delta 적용 ──
        world_after = _apply_delta(world_state, tool_result.state_delta, assets)

        # ── Step 6: EndingChecker - 엔딩 체크 ──
        ending_result = check_ending(world_after, assets)
        ending_info = None
        if ending_result.reached:
            ending_info = {
                "ending_id": ending_result.ending.ending_id,
                "name": ending_result.ending.name,
                "epilogue_prompt": ending_result.ending.epilogue_prompt,
            }
            if ending_result.triggered_delta:
                _apply_delta(world_after, ending_result.triggered_delta, assets)

        # ── Step 7: NarrativeLayer - 나레이션 생성 ──
        try:
            narrative_layer = get_narrative_layer()
            if ending_info:
                narrative = narrative_layer.render_ending(
                    ending_info,
                    world_after,
                    assets,
                )
            else:
                narrative = narrative_layer.render(
                    world_state=world_after,
                    assets=assets,
                    event_description=tool_result.event_description,
                    state_delta=tool_result.state_delta,
                )
        except ImportError as e:
            print(f"[GameService] NarrativeLayer skipped due to missing dependency: {e}")
            narrative = ""
        except Exception as e:
             print(f"[GameService] NarrativeLayer failed: {e}")
             narrative = ""
        
        # TODO 
        cls._world_state_to_games(game, world_after, assets)

        # 6. 저장
        user_content = input_data.chat_input

        if game.world_meta_data and "state" in game.world_meta_data:
            current_turn = game.world_meta_data["state"].get("turn", 1)
        create_chat_log(
            db, game_id, LogType.DIALOGUE, "Player", user_content, current_turn
        )
        
        # System Narrative Logging
        create_chat_log(
            db, game_id, LogType.NARRATIVE, "System", narrative, world_after.turn
        )

        crud_game.update_game(db, game)

        return StepResponseSchema(
            narrative=narrative,
            ending_info=ending_info,
            state_result=tool_result.state_delta,
            debug=debug,
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
        debug: Dict[str, Any] = {"game_id": game_id, "steps": []}

        # ── Step 1: Scenario → ScenarioAssets ──
        assets = _scenario_to_assets(game)

        # ── Step 2: Games → WorldStatePipeline ──
        world_state = cls._create_world_state(game)
        debug["turn_before"] = world_state.turn

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
        

        # ── Step 5: Date Increment & Delta 적용 ──
        # 밤이 지나면 날짜(date)가 바뀜
        current_date = world_state.date
        world_state.date = current_date + 1
        logger.info(f"Date incremented: {current_date} -> {world_state.date}")

        world_after = _apply_delta(world_state, night_result.night_delta, assets)

        # ── Step 6: EndingChecker - 엔딩 체크 ──
        ending_result = check_ending(world_after, assets)
        ending_info = None
        if ending_result.reached:
            ending_info = {
                "ending_id": ending_result.ending.ending_id,
                "name": ending_result.ending.name,
                "epilogue_prompt": ending_result.ending.epilogue_prompt,
            }
            if ending_result.triggered_delta:
                _apply_delta(world_after, ending_result.triggered_delta, assets)

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

        # ── Step 8: WorldStatePipeline → DB 반영 + 저장 ──
        cls._world_state_to_games(game, world_after, assets)
        
        # System Narrative Logging
        create_chat_log(
            db, game_id, LogType.NARRATIVE, "System", narrative, world_after.turn, {"conversation": night_result.night_conversation}
        )

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
        from app.schemas import GameClientSyncSchema
        from app.redis_client import get_redis_client

        print(f"[DEBUG] start_game called with game_id={game_id}")
        game = crud_game.get_game_by_id(db, game_id)
        print(f"[DEBUG] crud_game.get_game_by_id result: {game}")
        
        if not game:
            print(f"[DEBUG] Game not found for id {game_id}")
            raise ValueError(f"Game not found: {game_id}")

        client_sync_data = GameClientSyncSchema(
            game_id=game_id,
            user_id=game.user_id,
        )

        try:
            redis_client = get_redis_client()
            redis_key = f"game:{game_id}"
            redis_client.setex(redis_key, 3600, client_sync_data.json())
        except Exception as e:
            logger.warning(f"Failed to cache game state in Redis: {e}")

        return client_sync_data
