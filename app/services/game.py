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
from app.models import WorldState, NPCState, ToolResult
from app.day_controller import get_day_controller
from app.loader import ScenarioLoader, ScenarioAssets
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db_models.game import Games
from app.db_models.scenario import Scenario
from app.crud import game as crud_game
from app.loader import ScenarioAssets
from app.schemas.game_state import NPCState, WorldState, StateDelta
from app.schemas.request_response import TurnResult, NightTurnResult
from app.schemas.tool import ToolResult

# ============================================================
# Delta 적용 로직
# ============================================================

def _apply_delta(
    world_state: WorldState,
    delta_dict: Dict[str, Any],
    assets: ScenarioAssets | None = None,
) -> WorldState:
    """StateDelta를 WorldState에 적용 (in-place 변경 후 반환)"""
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

    @staticmethod
    def _create_world_state(game: Games) -> WorldState:
        """
        Game 모델에서 WorldState 객체를 생성합니다.
        """
        # 1. World Meta Data (Turn, Flags, Vars, Locks)
        meta = game.world_meta_data or {}
        state_data = meta.get("state", {})
        
        turn = state_data.get("turn", 1)
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
        inventory = player.get("inventory", [])

        # 3. NPC Data (NPCState)
        target_npc_data = game.npc_data or {"npcs": []}
        npcs = {}
        for npc in target_npc_data.get("npcs", []):
            nid = npc.get("npc_id")
            if not nid:
                continue
            
            stats = npc.get("stats", {})
            npcs[nid] = NPCState(
                npc_id=nid,
                trust=stats.get("trust", 0),
                fear=stats.get("fear", 0),
                suspicion=stats.get("suspicion", 0),
                humanity=stats.get("humanity", 10),
                extras=npc # 전체 데이터를 extras로 저장하거나 필요한거만 넣을 수 있음
            )

        return WorldState(
            turn=turn,
            npcs=npcs,
            flags=flags,
            inventory=inventory,
            locks=locks,
            vars=vars_
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
    ) -> TurnResult:
        """
        필요한 인자
        1. 유저 입력
        2. game state data
        3. 시나리오 에셋
        낮 파이프라인 실행:
        LockManager → DayController → EndingChecker → NarrativeLayer
        """

        ## 임시 출력용 input_dict
        print("\n\n\n")
        print("input_data: ", input_data)
        print("\n\n\n")

        # 2. WorldState 생성
        world_state = cls._create_world_state(game)

        # 3. Scenario Assets 로드
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

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)
        debug["steps"].append({
            "step": "lock_check",
            "newly_unlocked": [info.info_id for info in lock_result.newly_unlocked],
        })

        # ── Step 4: DayController - 낮 턴 실행 ──
        user_text = input_data.get("chat_input", "")
        day_controller = get_day_controller()
        tool_result: ToolResult = day_controller.process(
            user_text,
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
        mock_day_controller_result = ToolResult(
            event_description=[
                "플레이어가 새엄마에게 말을 걸었습니다.",
                "새엄마는 경계하는 눈빛을 보였습니다."
            ],
            state_delta={
                "npc_stats": {
                    "stepmother": { "trust": 2, "suspicion": 5 },
                    "brother": { "fear": -1 }
                },
                "flags": { "met_mother": True, "heard_rumor": True },
                "inventory_add": ["old_key", "strange_note"],
                "inventory_remove": ["apple"],
                "locks": { "basement_door": False },
                "vars": { "investigation_progress": 10 },
                "turn_increment": 1
            },
            memory={
                "last_interaction": "talked_to_mother",
                "clue_found": "old_key"
            }
        )
        
        print(f"[GameService] DayController Result: {tool_result}")


        # ── Step 5: Delta 적용 ──
        world_after = _apply_delta(world_state, tool_result.state_delta, assets)
        debug["turn_after"] = world_after.turn

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

        debug["steps"].append({
            "step": "ending_check",
            "reached": ending_result.reached,
        })

        # ── Step 7: NarrativeLayer - 나레이션 생성 ──
        narrative_layer = get_narrative_layer()
        if ending_info:
            narrative = narrative_layer.render_ending(
                ending_info,
                world_after,
                assets,
            )
        else:
            narrative = narrative_layer.render_day(
                tool_result.event_description,
                tool_result.state_delta,
                world_after,
                assets,
            )

        # TODO : WorldState -> game 으로 형식 변경 후 저장

        # 6. 저장
        crud_game.update_game(db, game)

        # TODO : return 형식 변경 -> TurnResult
        #return tool_result.__dict__ # Dict 반환
        return mock_day_controller_result.__dict__

    @classmethod
    def process_night(
        cls,
        db: Session,
        game_id: int,
        game: Games,
    ) -> NightTurnResult:
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
        # TODO : process_turn()과 동일하게 STEP 1, 2, 8 변경
        debug: Dict[str, Any] = {"game_id": game_id, "steps": []}

        # ── Step 1: Scenario → ScenarioAssets ──
        scenario: Scenario = game.scenario
        assets = _scenario_to_assets(scenario)

        # ── Step 2: Games → WorldState ──
        world_state = _games_to_world_state(game)
        debug["turn_before"] = world_state.turn

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)
        debug["steps"].append({
            "step": "lock_check",
            "newly_unlocked": [info.info_id for info in lock_result.newly_unlocked],
        })

        # ── Step 4: NightController - 밤 턴 실행 ──
        night_controller = get_night_controller()
        night_result = night_controller.process(world_state, assets)
        debug["steps"].append({
            "step": "night_turn",
            "night_delta": night_result.night_delta,
            "utterance_count": len(night_result.night_conversation),
        })

        # ── Step 5: Delta 적용 ──
        world_after = _apply_delta(world_state, night_result.night_delta, assets)
        debug["turn_after"] = world_after.turn

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

        debug["steps"].append({
            "step": "ending_check",
            "reached": ending_result.reached,
        })

        # ── Step 7: NarrativeLayer - 나레이션 생성 ──
        narrative_layer = get_narrative_layer()
        if ending_info:
            narrative = narrative_layer.render_ending(
                ending_info,
                world_after,
                assets,
            )
        else:
            narrative = narrative_layer.render_night(
                world_after,
                assets,
                night_result.night_conversation,
            )

        # ── Step 8: WorldState → DB 반영 + 저장 ──
        _world_state_to_games(game, world_after)
        crud_game.update_game(db, game)

        logger.info(
            f"Night completed: game={game_id}, "
            f"turn={world_after.turn}, ending={ending_result.reached}"
        )

        return NightTurnResult(
            dialogue=narrative,
            night_conversation=night_result.night_conversation,
            ending=ending_info,
            debug=debug,
        )

    @staticmethod
    def start_game(db: Session, game_id: int):
        """게임 id를 받아서 진행된 게임을 불러옴"""
        from app.schemas import GameClientSyncSchema, WorldDataSchema, PlayerSchema, NpcCollectionSchema
        from app.redis_client import get_redis_client

        game = crud_game.get_game_by_id(db, game_id)
        if not game:
            raise ValueError(f"Game not found: {game_id}")

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
