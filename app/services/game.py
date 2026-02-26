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
from app.database import SessionLocal
from sqlalchemy.orm.attributes import flag_modified

from app.db_models.game import Games
from app.crud import game as crud_game
from app.redis_client import get_redis_client

from app.schemas.client_sync import GameClientSyncSchema
from app.schemas.request_response import StepRequestSchema, StepResponseSchema, NightResponseResult, NightDialogue
from app.schemas.status import ItemStatus, LogType, NPCStatus
from app.schemas.game_state import NPCState, WorldStatePipeline, StateDelta
from app.schemas.tool import ToolResult
from app.schemas.night import NightResult
from app.schemas.status import GameStatus

from app.crud.chat_log import create_chat_log
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
from app.loader import ScenarioLoader, ScenarioAssets
from app.lock_manager import get_lock_manager, format_unlock_events
from app.ending_checker import check_ending
from app.narrative import get_narrative_layer

import logging

logger=logging.getLogger(__name__)

def _scenario_to_assets(game: Games) -> ScenarioAssets:
    assets = None
    if game.scenario and game.scenario.world_asset_data:
        try:
            # DB에 저장된 에셋 사용
            # world_asset_data는 dict 형태여야 함
            assets = ScenarioAssets(**game.scenario.world_asset_data)
            assets = ScenarioAssets(**game.scenario.world_asset_data)
            logger.debug(f"[GameService] Loaded assets from DB for scenario: {game.scenario.title}")
        except Exception as e:
            logger.error(f"[GameService] Failed to load assets from DB: {e}")

    if not assets:
        # Fallback: 파일 로드
        scenario_title = game.scenario.title if game.scenario else "coraline"
        project_root = Path(__file__).parent.parent.parent
        scenarios_dir = project_root / "scenarios"
        loader = ScenarioLoader(base_path=scenarios_dir)
        assets = loader.load(scenario_title)
        logger.debug(f"[GameService] Loaded assets from FILE for scenario: {scenario_title}")

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

    # 1b. NPC status changes (enum, not numeric)
    for npc_id, new_status in delta.npc_status_changes.items():
        if npc_id in world_state.npcs:
            try:
                world_state.npcs[npc_id].status = NPCStatus(new_status)
            except ValueError:
                logger.warning(f"Invalid NPC status: {new_status}")

    # 1c. NPC phase changes
    for npc_id, new_phase_id in delta.npc_phase_changes.items():
        if npc_id in world_state.npcs:
            prev = world_state.npcs[npc_id].current_phase_id
            world_state.npcs[npc_id].current_phase_id = new_phase_id
            if prev != new_phase_id:
                logger.info(f"[apply_delta] phase 전환: npc={npc_id} | {prev} → {new_phase_id}")

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

    """
    Game 모델에서 WorldStatePipeline 객체를 생성합니다.
    """
    @staticmethod
    def _create_world_state(game: Games) -> WorldStatePipeline:
        # 1. World Meta Data (Turn, Flags, Vars, Locks)
        meta = game.world_meta_data or {}
        state_data = meta.get("state", {})
    
        turn = state_data.get("turn", 1)
        # date removed (use vars['day'])
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
        
        # 3. NPC Data
        npcs = {}
        if game.npc_data and "npcs" in game.npc_data:
            for npc_info in game.npc_data["npcs"]:
                nid = npc_info.get("npc_id")
                if nid:
                    npcs[nid] = NPCState.from_dict(npc_info)

        return WorldStatePipeline(
            turn=turn,
            # date removed
            npcs=npcs,
            flags=flags,
            inventory=player.get("inventory", []),
            locks=locks,
            vars=vars_,
            day_action_log=day_action_log,
            player_location=player.get("current_node"),  # 저장된 플레이어 위치 복원
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
        # date removed (use vars['day'])
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

        # 플레이어 위치 저장
        if world_state.player_location:
            player["current_node"] = world_state.player_location

        # 2-0. Update Player Stats (Humanity)
        # vars에 humanity가 있다면 player.stats에도 동기화
        if "humanity" in world_state.vars:
            if "stats" not in player:
                player["stats"] = {}
            player["stats"]["humanity"] = world_state.vars["humanity"]

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

                # current_phase_id 업데이트 (NPCState 필드 → DB 최상위 키)
                npc_dict["current_phase_id"] = npc_state.current_phase_id

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

    @classmethod
    def process_turn(
        cls,
        db: Session,
        game_id: int,
        input_data: StepRequestSchema,
        game: Games = None, # Optional: only provided if fallback to DB occurs in router
    ) -> StepResponseSchema:
        """
        낮 파이프라인 실행:
        오직 Redis에서만 상태를 로드합니다! 
        Redis에 상태가 없을 경우 DB에서 게임을 조회하고 Redis를 갱신한 뒤 처리합니다.
        """
        debug: Dict[str, Any] = {"game_id": game_id, "steps": []}
        redis_client = get_redis_client()

        # ── Step 1: world state 생성 (Redis Only) ──
        cached_state = None
        load_source = "Redis"
        try:
            cached_state = redis_client.get_game_state(str(game_id))
        except Exception as e:
            logger.warning(f"Failed to get game state from Redis: {e}")

        if not cached_state:
            logger.warning(f"Redis cache MISS for game_id={game_id}! Falling back to DB load.")
            load_source = "DB_Fallback"
            if game is None:
                # 라우터에서 game을 넘기지 않은 경우 직접 조회해야 함
                game = crud_game.get_game_by_id(db, game_id)
                if not game:
                    raise ValueError(f"Game {game_id} not found in DB!")
                    
            world_state = cls._create_world_state(game)
        else:
            logger.debug(f"Loaded game state from Redis for game_id={game_id}")
            # Redis에 데이터가 있으면 DB 게임 모델을 가상으로 생성 (저장을 위해)
            if game is None:
                # DB 조회를 유예하거나 빈 껍데기를 쓸 수도 있지만, 
                # 나레이션이나 이력 저장을 위해 최소한의 DB 인스턴스가 필요할 수 있음.
                # 그러나 성능의 극대화를 위해 game 속성만 덮어씌움.
                game = Games(id=game_id)
                
            meta = cached_state.get("meta_data", {})
            npc_stats = cached_state.get("npc_stats", {})
            player_info = cached_state.get("player_info", {})
            
            game.world_meta_data = meta
            game.npc_data = {"npcs": list(npc_stats.values())}
            game.player_data = player_info

            world_state = cls._create_world_state(game)

        # ── Step 2: Scenario Assets 로드 ──
        # assets 로드 시 DB의 Scenario 객체가 필요할 수 있음
        # 만약 Redis 전용 모드에서 DB 접근이 막힌다면 문제가 됨
        # 그러나 _scenario_to_assets 안에는 file fallback(loader) 로직이 있음
        assets = _scenario_to_assets(game)

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)

        # ── Step 3.5: StatusEffectManager - 만료 효과 해제 ──
        from app.status_effect_manager import get_status_effect_manager
        sem = get_status_effect_manager()
        sem.tick(world_state.turn, world_state)

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
            "input": user_input,
            "intent": tool_result.intent,
            "events": tool_result.event_description,
        }
        world_after.day_action_log.append(day_log_entry)

        # ── Step 6: EndingChecker - 엔딩 체크 ──
        ending_result = check_ending(world_after, assets)
        ending_info = None
        if ending_result.reached:
            ending_info = {
                "ending_id": ending_result.ending.ending_id,
                "name": ending_result.ending.name,
                "epilogue_prompt": ending_result.ending.epilogue_prompt,
            }
            game.status = GameStatus.ENDING.value
            if ending_result.triggered_delta:
                game.status = GameStatus.ENDING.value
                _apply_delta(world_after, ending_result.triggered_delta.to_dict(), assets)

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
                    npc_response=tool_result.npc_response
                )
        except Exception as e:
             logger.error(f"[GameService] NarrativeLayer failed: {e}")
             narrative = ""
        
        # ── Step 7.5: Update Game Summary ──
        current_summary = game.summary
        if current_summary:
            game.summary = f"{current_summary}\n{narrative}"
        else:
            game.summary = narrative
        if game.id is not None and getattr(game, "_sa_instance_state", None) is not None:
             flag_modified(game, "summary")

        # ── Step 8: Update Game State & Cache ──
        # 로컬 객체 업데이트
        cls._world_state_to_games(game, world_after, assets)
        
        # Redis 캐시 갱신 (항상)
        try:
            npc_stats = {}
            if game.npc_data and "npcs" in game.npc_data:
                for npc in game.npc_data["npcs"]:
                    if "npc_id" in npc:
                        npc_stats[npc["npc_id"]] = npc
            
            redis_client.set_game_state(
                str(game_id),
                game.world_meta_data,
                npc_stats,
                game.player_data
            )
            logger.debug(f"Updated Redis cache for game_id={game_id}")
        except Exception as e:
            logger.error(f"Failed to update Redis cache: {e}")

        # 6. 저장 (DB) - Redis 온리(Only) 정책에 따라 매턴 동기식 DB 저장을 제거하거나 분리.
        #    사용자 요구사항에 따라: Redis에서만 데이터 Fetch -> 로직 처리 -> Redis 재저장.
        #    DB 저장은 제외 (또는 비동기 처리)
        
        # 다만 현재 로그 테이블은 분리되어 있어서 로그만 따로 쌓음 (DB 병목 요소 중 하나지만 로그 유지를 위해 남김)
        if load_source == "DB_Fallback":
            # 폴백이었으면 DB에 최신 상태 한번 저장해줌
            if game.id is not None and getattr(game, "_sa_instance_state", None) is not None:
                db.commit()

        user_content = input_data.chat_input
        current_turn = world_after.turn

        if load_source == "DB_Fallback":
            log_db = SessionLocal()
            try:
                create_chat_log(
                    log_db, game_id, LogType.DIALOGUE, "Player", user_content, current_turn
                )
                
                # System Narrative Logging
                create_chat_log(
                    log_db, game_id, LogType.NARRATIVE, "System", narrative, world_after.turn
                )
                
                # Save summary along with the logs using this separate session
                log_game = log_db.query(Games).filter(Games.id == game_id).first()
                if log_game:
                    log_game.summary = game.summary
                    flag_modified(log_game, "summary")
                    log_db.commit()
            finally:
                log_db.close()
        if game.status == GameStatus.ENDING.value:
            if game.id is not None and getattr(game, "_sa_instance_state", None) is not None:
                 db.commit()
            redis_client.delete_game_state(str(game_id))
            logger.info(f"Game {game_id} ended at turn {world_after.turn}. Synced to DB and removed from Redis.")
        else:
            logger.info(f"Turn {world_after.turn} processed (Source: {load_source}, Redis: Updated)")

        # ── Assemble state_result for frontend ──
        _delta = tool_result.state_delta

        sr_npc_stats = _delta.get("npc_stats") or None
        sr_flags = _delta.get("flags") or None
        sr_inventory_add = _delta.get("inventory_add") or None
        sr_inventory_remove = _delta.get("inventory_remove") or None

        sr_npc_disabled_states = None
        active_effects = world_after.vars.get("status_effects", [])
        if active_effects:
            disabled = {}
            for eff in active_effects:
                if isinstance(eff, dict):
                    npc_id = eff.get("target_npc_id")
                    if npc_id:
                        disabled[npc_id] = {
                            "is_disabled": True,
                            "remaining_turns": max(0, eff.get("expires_at_turn", 0) - world_after.turn),
                            "reason": eff.get("applied_status", "unknown"),
                        }
            if disabled:
                sr_npc_disabled_states = disabled

        sr_vars = dict(_delta.get("vars", {}))
        sr_humanity = sr_vars.pop("humanity", None)
        sr_vars.pop("status_effects", None)

        current_node = None
        if isinstance(game.player_data, dict):
            current_node = game.player_data.get("current_node")

        state_result = {
            "npc_stats": sr_npc_stats,
            "flags": sr_flags,
            "inventory_add": sr_inventory_add,
            "inventory_remove": sr_inventory_remove,
            "item_state_changes": None,
            "npc_disabled_states": sr_npc_disabled_states,
            "humanity": sr_humanity,
            "current_node": current_node,
            "vars": sr_vars if sr_vars else {},
        }

        return StepResponseSchema(
            narrative=narrative,
            ending_info=ending_info,
            state_result=state_result,
            debug=debug,
        )

    @classmethod
    def process_turn_db_only(
        cls,
        db: Session,
        game_id: int,
        input_data: StepRequestSchema,
        game: Games,
    ) -> StepResponseSchema:
        """
        낮 파이프라인 실행:
        LockManager → DayController → EndingChecker → NarrativeLayer → DB/Redis 저장
        """
        debug: Dict[str, Any] = {"game_id": game_id, "steps": []}
        redis_client = get_redis_client()

        # ── Step 1: world state 생성 (DB 단독) ──
        load_source = "DB_ONLY"
        logger.debug(f"Loading game state from DB exclusively for game_id={game_id}")
        world_state = cls._create_world_state(game)

        # ── Step 2: Scenario Assets 로드 ──
        assets = _scenario_to_assets(game)

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)

        # ── Step 3.5: StatusEffectManager - 만료 효과 해제 ──
        from app.status_effect_manager import get_status_effect_manager
        sem = get_status_effect_manager()
        sem.tick(world_state.turn, world_state)

        # ── Step 3.7: 플레이어 위치 갱신 (프론트에서 받은 값 우선) ──
        if input_data.player_location:
            world_state.player_location = input_data.player_location

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

        # ── Step 5.7: LockManager - Delta 적용 후 추가 해금 체크 ──
        lock_result_post = lock_manager.check_unlocks(world_after, locks_data)
        all_newly_unlocked = lock_result.newly_unlocked + lock_result_post.newly_unlocked
        if all_newly_unlocked:
            unlock_events = format_unlock_events(all_newly_unlocked)
            tool_result.event_description.extend(unlock_events)
            logger.info(f"[LockManager] {len(all_newly_unlocked)}건 해금 → event_description 추가: {unlock_events}")

        # ── Step 5.8: day_action_log 축적 (밤 가족회의 안건용) ──
        day_log_entry = {
            "turn": world_after.turn,
            "input": user_input,
            "intent": tool_result.intent,
            "events": tool_result.event_description,
        }
        world_after.day_action_log.append(day_log_entry)

        # ── Step 6: EndingChecker - 엔딩 체크 ──
        ending_result = check_ending(world_after, assets)
        ending_info = None
        if ending_result.reached:
            ending_info = {
                "ending_id": ending_result.ending.ending_id,
                "name": ending_result.ending.name,
                "epilogue_prompt": ending_result.ending.epilogue_prompt,
            }
            game.status = GameStatus.ENDING.value
            if ending_result.triggered_delta:
                game.status = GameStatus.ENDING.value
                _apply_delta(world_after, ending_result.triggered_delta.to_dict(), assets)

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
                    npc_response=tool_result.npc_response
                )
        except Exception as e:
             logger.error(f"[GameService] NarrativeLayer failed: {e}")
             narrative = ""
        
        # ── Step 7.5: Update Game Summary ──
        current_summary = game.summary
        if current_summary:
            game.summary = f"{current_summary}\n{narrative}"
        else:
            game.summary = narrative
        flag_modified(game, "summary")

        # ── Step 8: Update Game State & Cache ──
        # DB 모델 객체 업데이트 (JSON 구조체 갱신)
        cls._world_state_to_games(game, world_after, assets)
        
        # Redis 캐시 업데이트 생략 (DB 전용 모드)

        # 6. 저장 (DB) - 주기적 동기화 구현 전까지는 안전하게 매 턴 저장 유지
        # TODO: 추후 Background Task로 이관 시 이 부분 조건부 실행 검토
        user_content = input_data.chat_input

        if game.world_meta_data and "state" in game.world_meta_data:
            current_turn = game.world_meta_data["state"].get("turn", 1)
            


        log_db = SessionLocal()
        try:
            create_chat_log(
                log_db, game_id, LogType.DIALOGUE, "Player", user_content, current_turn
            )
            
            # System Narrative Logging
            create_chat_log(
                log_db, game_id, LogType.NARRATIVE, "System", narrative, world_after.turn
            )
            
            # Save summary along with the logs using this separate session
            log_game = log_db.query(Games).filter(Games.id == game_id).first()
            if log_game:
                log_game.summary = game.summary
                flag_modified(log_game, "summary")
                log_db.commit()
        finally:
            log_db.close()

        if game.status == GameStatus.ENDING.value:
            db.commit()
            redis_client.delete_game_state(str(game_id))
            logger.info(f"Game {game_id} ended at turn {world_after.turn}. Synced to DB and removed from Redis.")
        else:
            logger.info(f"Turn {world_after.turn} processed (Source: {load_source}, Redis: Updated)")

        # ── Assemble state_result for frontend ──
        _delta = tool_result.state_delta

        sr_npc_stats = _delta.get("npc_stats") or None
        sr_flags = _delta.get("flags") or None
        sr_inventory_add = _delta.get("inventory_add") or None
        sr_inventory_remove = _delta.get("inventory_remove") or None

        sr_npc_disabled_states = None
        active_effects = world_after.vars.get("status_effects", [])
        if active_effects:
            disabled = {}
            for eff in active_effects:
                if isinstance(eff, dict):
                    npc_id = eff.get("target_npc_id")
                    if npc_id:
                        disabled[npc_id] = {
                            "is_disabled": True,
                            "remaining_turns": max(0, eff.get("expires_at_turn", 0) - world_after.turn),
                            "reason": eff.get("applied_status", "unknown"),
                        }
            if disabled:
                sr_npc_disabled_states = disabled

        sr_vars = dict(_delta.get("vars", {}))
        sr_humanity = sr_vars.pop("humanity", None)
        sr_vars.pop("status_effects", None)

        # player_data에서 현재 current_node 추출
        current_node = None
        if isinstance(game.player_data, dict):
            current_node = game.player_data.get("current_node")

        state_result = {
            "npc_stats": sr_npc_stats,
            "flags": sr_flags,
            "inventory_add": sr_inventory_add,
            "inventory_remove": sr_inventory_remove,
            "item_state_changes": None,
            "npc_disabled_states": sr_npc_disabled_states,
            "humanity": sr_humanity,
            "current_node": current_node,
            "vars": sr_vars if sr_vars else {},
        }

        return StepResponseSchema(
            narrative=narrative,
            ending_info=ending_info,
            state_result=state_result,
            debug=debug,
        )

    @staticmethod
    def _create_night_response_data(narrative: str, night_result: NightResult) -> Dict[str, Any]:
        """NightResponseResult 생성을 위한 데이터 가공"""
        
        # 1. Narrative: 전체 텍스트에서 '---' 다음의 첫 실제 문장 추출
        # 공백/개행 제외하고 의미 있는 라인만 필터링
        lines = [line.strip() for line in narrative.split("\n") if line.strip()]
        
        # lines[0]은 보통 '---' 구분선이므로 lines[1]을 가져옴
        if len(lines) >= 2:
            summary_narrative = lines[1]
        elif len(lines) == 1:
            summary_narrative = lines[0]
        else:
            summary_narrative = "밤이 지났습니다."

        # 2. Dialogues: NightResult의 conversation 데이터 사용
        # Regex 파싱 대신 원본 데이터를 사용하여 안정성 확보
        # 클라이언트에서 text 부분은 마스킹(...) 처리 후 클릭 시 해제
        dialogues = []
        if night_result.night_conversation:
            for utter in night_result.night_conversation:
                speaker = utter.get("speaker", "Unknown")
                text = utter.get("text", "...")
                dialogues.append(NightDialogue(speaker_name=speaker, dialogue=text))

        return {
            "narrative": summary_narrative,
            "dialogues": dialogues,
        }


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
        redis_client = get_redis_client()

        # ── Step 1: world state 생성 (Redis 우선) ──
        cached_state = None
        load_source = "DB"
        try:
            cached_state = redis_client.get_game_state(str(game_id))
        except Exception as e:
            logger.warning(f"Failed to get game state from Redis: {e}")

        if cached_state:
            load_source = "Redis"
            logger.debug(f"Loaded game state from Redis for game_id={game_id}")
            meta = cached_state.get("meta_data", {})
            npc_stats = cached_state.get("npc_stats", {})
            player_info = cached_state.get("player_info", {})
            
            # DB 모델에 Redis 데이터 반영 (참조용)
            game.world_meta_data = meta
            game.npc_data = {"npcs": list(npc_stats.values())}
            game.player_data = player_info
            
            # 공통 함수를 사용하여 WorldState 생성
            world_state = cls._create_world_state(game)
        else:
            logger.debug(f"Cache miss for game_id={game_id}, loading from DB")
            world_state = cls._create_world_state(game)

        debug["turn_before"] = world_state.turn

        # ── Step 2: Scenario Assets 로드 ──
        assets = _scenario_to_assets(game)

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
        world_after = _apply_delta(world_state, night_result.night_delta, assets)
        current_day = world_after.vars.get("day", 1)
        if isinstance(current_day, int):
            world_after.vars["day"] = current_day + 1
        else:
            world_after.vars["day"] = 1
            
        logger.info(f"Day incremented: {world_after.vars['day']}")

        # ── Step 5.7: LockManager - Delta 적용 후 추가 해금 체크 ──
        lock_result_post = lock_manager.check_unlocks(world_after, locks_data)
        all_newly_unlocked = lock_result.newly_unlocked + lock_result_post.newly_unlocked
        if all_newly_unlocked:
            unlock_events = format_unlock_events(all_newly_unlocked)
            if night_result.night_description is None:
                night_result.night_description = []
            night_result.night_description.extend(unlock_events)
            logger.info(f"[LockManager] 밤 {len(all_newly_unlocked)}건 해금 → night_description 추가: {unlock_events}")

        # ── Step 6: EndingChecker - 엔딩 체크 (has_item 조건 스킵) ──
        ending_result = check_ending(world_after, assets, skip_has_item=True)
        ending_info = ending_result.to_ending_info_dict() if ending_result.reached else None
        if ending_result.reached:
            game.status = GameStatus.ENDING.value
            if ending_result.triggered_delta:
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

        # ── Step 7.5: Update Game Summary ──
        current_summary = game.summary or ""
        if isinstance(current_summary, dict) or isinstance(current_summary, list):
            current_summary = ""
            
        if current_summary:
            game.summary = f"{current_summary}\n{narrative}"
        else:
            game.summary = narrative
        flag_modified(game, "summary")

        # ── Step 7.8: day_action_log 초기화 (다음 낮을 위해) ──
        world_after.day_action_log = []

        # ── Step 8: WorldStatePipeline → DB 반영 + Cache Update ──
        cls._world_state_to_games(game, world_after, assets)
        
        # Redis 캐시 업데이트
        try:
            npc_stats = {}
            if game.npc_data and "npcs" in game.npc_data:
                for npc in game.npc_data["npcs"]:
                    if "npc_id" in npc:
                        npc_stats[npc["npc_id"]] = npc
            
            redis_client.set_game_state(
                str(game_id),
                game.world_meta_data,
                npc_stats,
                game.player_data
            )
            logger.debug(f"Updated Redis cache for game_id={game_id}")
        except Exception as e:
            logger.error(f"Failed to update Redis cache: {e}")

        # Response 구성
        response_data = cls._create_night_response_data(narrative, night_result)
        
        # System Narrative Logging
        # NightDialogue 객체는 JSON 직렬화가 안되므로 dict로 변환
        dialogues_dict = [d.model_dump() for d in response_data["dialogues"]]
        
        log_db = SessionLocal()
        try:
            create_chat_log(
                log_db, game_id, LogType.NIGHT_EVENT, "System", response_data["narrative"], world_after.turn, {"dialogues": dialogues_dict}
            )
            
            # Save summary along with the logs using this separate session
            log_game = log_db.query(Games).filter(Games.id == game_id).first()
            if log_game:
                log_game.summary = game.summary
                flag_modified(log_game, "summary")
                log_db.commit()
        finally:
            log_db.close()

        # [PERFORMANCE] Background Sync로 이관 (Redis Only Update)
        # crud_game.update_game(db, game)
        if game.status == GameStatus.ENDING.value:
            db.commit()
            redis_client.delete_game_state(str(game_id))
            logger.info(f"Game {game_id} ended during night. Synced to DB and removed from Redis.")
        else:
            logger.info(
                f"Night completed: game={game_id}, "
                f"turn={world_after.turn}, ending={ending_result.reached}, Source={load_source}"
            )

        # ── Assemble state_result for frontend (night) ──
        _night_delta = night_result.night_delta

        sr_npc_stats = _night_delta.get("npc_stats") or None
        sr_flags = _night_delta.get("flags") or None
        sr_inventory_add = _night_delta.get("inventory_add") or None
        sr_inventory_remove = _night_delta.get("inventory_remove") or None

        sr_npc_disabled_states = None
        active_effects = world_after.vars.get("status_effects", [])
        if active_effects:
            disabled = {}
            for eff in active_effects:
                if isinstance(eff, dict):
                    npc_id = eff.get("target_npc_id")
                    if npc_id:
                        disabled[npc_id] = {
                            "is_disabled": True,
                            "remaining_turns": max(0, eff.get("expires_at_turn", 0) - world_after.turn),
                            "reason": eff.get("applied_status", "unknown"),
                        }
            if disabled:
                sr_npc_disabled_states = disabled

        sr_vars = dict(_night_delta.get("vars", {}))
        sr_humanity = sr_vars.pop("humanity", None)
        sr_vars.pop("status_effects", None)

        # player_data에서 현재 current_node 추출
        current_node = None
        if isinstance(game.player_data, dict):
            current_node = game.player_data.get("current_node")

        night_state_result = {
            "npc_stats": sr_npc_stats,
            "flags": sr_flags,
            "inventory_add": sr_inventory_add,
            "inventory_remove": sr_inventory_remove,
            "item_state_changes": None,
            "npc_disabled_states": sr_npc_disabled_states,
            "humanity": sr_humanity,
            "current_node": current_node,
            "vars": sr_vars if sr_vars else {},
        }

        debug["turn_after"] = world_after.turn

        return NightResponseResult(
            narrative=response_data["narrative"],
            dialogues=response_data["dialogues"],
            ending_info=ending_info,
            state_result=night_state_result,
            debug=debug,
            phase_changes=night_result.phase_changes,
        )

    @staticmethod
    def quit_game(db: Session, game_id: int):
        """
        사용자가 게임을 중간에 종료(Quit)할 때 호출됨.
        Redis에서 캐싱된 데이터를 DB에 플러시(저장)하고 캐시를 삭제함.
        게임의 상태(status)는 계속 진행 가능하도록 변경하지 않음.
        """
        game = crud_game.get_game_by_id(db, game_id)
        if not game:
            raise ValueError(f"Game not found: {game_id}")
            
        redis_client = get_redis_client()
        cached_state = redis_client.get_game_state(str(game_id))
        
        if cached_state:
            # DB 모델에 최신 Redis 데이터 반영
            meta = cached_state.get("meta_data", {})
            npc_stats = cached_state.get("npc_stats", {})
            player_info = cached_state.get("player_info", {})
            
            game.world_meta_data = meta
            game.npc_data = {"npcs": list(npc_stats.values())}
            game.player_data = player_info
            
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(game, "world_meta_data")
            flag_modified(game, "npc_data")
            flag_modified(game, "player_data")
            
            # DB에 커밋
            db.commit()
            
            # Redis 정리
            redis_client.delete_game_state(str(game_id))
            logger.info(f"Game {game_id} saved to DB and Redis cache cleared on quit.")

    @staticmethod
    def start_game(db: Session, game_id: int):
        """게임 id를 받아서 진행된 게임을 불러옴"""
        from app.schemas.client_sync import GameClientSyncSchema
        from app.redis_client import get_redis_client

        logger.info(f"[GameService] start_game called with game_id={game_id}")
        game = crud_game.get_game_by_id(db, game_id)
        
        if not game:
            logger.error(f"[GameService] Game not found for id {game_id}")
            raise ValueError(f"Game not found: {game_id}")

        # Redis에 게임 상태 캐싱
        try:
            redis_client = get_redis_client()
            
            # Serialize data for Redis
            meta_data = game.world_meta_data or {}
            
            # NPC Data extraction
            npc_stats = {}
            if game.npc_data and "npcs" in game.npc_data:
                for npc in game.npc_data["npcs"]:
                    if "npc_id" in npc:
                        npc_stats[npc["npc_id"]] = npc
            
            player_info = game.player_data or {}
            
            # Cache to Redis
            redis_client.set_game_state(
                str(game_id),
                meta_data,
                npc_stats,
                player_info
            )
            logger.info(f"[GameService] Game state cached in Redis for game_id={game_id}")
            
        except Exception as e:
            logger.warning(f"[GameService] Failed to cache game state in Redis: {e}")

        # Client Sync Data (for frontend)
        client_sync_data = GameClientSyncSchema(
            game_id=game_id,
            user_id=game.user_id,
        )
        
        return client_sync_data
    # 텍스트로 맵 이동을 받으면 플레이어의 위치를 그 맵으로 변경
    @staticmethod
    def change_location(db: Session, game_id: int, location: str):
        redis_client = get_redis_client()
        
        try:
            player_info = redis_client.get_player_info(str(game_id))
            if player_info is None:
                logger.warning(f"No player info found for game_id={game_id} in Redis, reloading from DB.")
                GameService.start_game(db, game_id)
                player_info = redis_client.get_player_info(str(game_id))
                if player_info is None:
                    return game_id
                
            # 전달받은 location으로 현재 노드 변경
            player_info["current_node"] = location
            
            # Redis에 상태 저장 (일부 업데이트)
            redis_client.update_player_info(str(game_id), player_info)
            logger.info(f"Updated current_node to {location} for game_id={game_id} in Redis")
            
        except Exception as e:
            logger.error(f"Failed to update location for game_id={game_id} in Redis: {e}")

        return game_id
    

    # 엔딩이 난 게임을 소설로 만들기
    @staticmethod
    def make_novel(game_id: int) -> str:
        from app.database import SessionLocal
        from app.crud.chat_log import get_chat_logs_by_game_id
        from app.schemas.status import LogType
        
        db = SessionLocal()
        try:
            logs = get_chat_logs_by_game_id(db, game_id)
            if not logs:
                return "아직 기록된 이야기가 없습니다."
            
            novel_lines = ["이것은 당신이 만들어낸 이야기"]
            for log in logs:
                content = log.content.strip() if log.content else ""
                
                if log.type == LogType.DIALOGUE:
                    # 플레이어의 대사/행동
                    novel_lines.append(f'\n"주인공 : {content}"\n')
                elif log.type == LogType.NARRATIVE:
                    # 시스템의 나레이션 (상황 설명)
                    novel_lines.append(content)
                elif log.type == LogType.NIGHT_EVENT:
                    # 밤 이벤트
                    novel_lines.append(f'\n[밤이 되었습니다...]\n{content}')
                    
                    # 밤 대화록 (metadata_의 dialogues) -> 얜 나중에 생각해봄
                    if log.metadata_ and "dialogues" in log.metadata_:
                        for d in log.metadata_["dialogues"]:
                            speaker = d.get("speaker_name", "누군가")
                            text = d.get("dialogue", "...")
                            if speaker and text:
                                novel_lines.append(f'{speaker}: "{text}"')
                else:
                    novel_lines.append(content)
                    
            return "\n".join(novel_lines).strip()
        finally:
            db.close()
