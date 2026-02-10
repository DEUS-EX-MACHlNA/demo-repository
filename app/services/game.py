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

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.db_models.game import Games
from app.db_models.scenario import Scenario
from app.crud import game as crud_game
from app.loader import ScenarioAssets
from app.schemas.game_state import NPCState, WorldState, StateDelta
from app.schemas.request_response import TurnResult, NightTurnResult
from app.schemas.tool import ToolResult

from app.lock_manager import get_lock_manager
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
from app.ending_checker import check_ending
from app.narrative import get_narrative_layer

logger = logging.getLogger(__name__)


# ============================================================
# 변환 헬퍼: DB ↔ WorldState
# ============================================================

def _games_to_world_state(game: Games) -> WorldState:
    """Games DB 모델 → WorldState 변환"""
    snapshot = game.world_data_snapshot or {}
    state_data = snapshot.get("state", {})
    player = game.player_data or {}
    npc_raw = game.npc_data or {"npcs": []}

    # NPC 리스트 → {npc_id: NPCState} dict
    npcs: Dict[str, NPCState] = {}
    for npc in npc_raw.get("npcs", []):
        npc_id = npc.get("npc_id")
        if npc_id:
            npcs[npc_id] = NPCState(
                npc_id=npc_id,
                stats=npc.get("stats", {}),
                memory=npc.get("memory", {}),
            )

    # Locks 리스트 → {info_id: is_unlocked} dict
    locks_data = snapshot.get("locks", {})
    locks: Dict[str, bool] = {}
    for lock_item in locks_data.get("locks", []):
        info_id = lock_item.get("info_id")
        if info_id:
            locks[info_id] = lock_item.get("is_unlocked", False)

    return WorldState(
        turn=state_data.get("turn", 1),
        npcs=npcs,
        flags=state_data.get("flags", {}),
        inventory=player.get("inventory", []),
        locks=locks,
        vars=state_data.get("vars", {}),
    )


def _world_state_to_games(game: Games, world_state: WorldState) -> None:
    """WorldState → Games DB 모델에 반영 (in-place 변경)"""
    # (1) world_data_snapshot 업데이트
    snapshot = copy.deepcopy(game.world_data_snapshot or {})

    state_data = snapshot.get("state", {})
    state_data["turn"] = world_state.turn
    state_data["flags"] = world_state.flags
    state_data["vars"] = world_state.vars
    snapshot["state"] = state_data

    # locks: WorldState의 {info_id: bool} → DB의 locks 리스트에 반영
    locks_wrapper = snapshot.get("locks", {})
    locks_list = locks_wrapper.get("locks", [])
    for lock_item in locks_list:
        info_id = lock_item.get("info_id")
        if info_id and info_id in world_state.locks:
            lock_item["is_unlocked"] = world_state.locks[info_id]
    locks_wrapper["locks"] = locks_list
    snapshot["locks"] = locks_wrapper

    game.world_data_snapshot = snapshot
    flag_modified(game, "world_data_snapshot")

    # (2) player_data 업데이트
    p_data = copy.deepcopy(game.player_data or {})
    p_data["inventory"] = world_state.inventory
    game.player_data = p_data
    flag_modified(game, "player_data")

    # (3) npc_data 업데이트
    n_data = copy.deepcopy(game.npc_data or {"npcs": []})
    npc_list = n_data.get("npcs", [])
    for npc in npc_list:
        npc_id = npc.get("npc_id")
        if npc_id and npc_id in world_state.npcs:
            ws_npc = world_state.npcs[npc_id]
            npc["stats"] = ws_npc.stats
            npc["memory"] = ws_npc.memory
    n_data["npcs"] = npc_list
    game.npc_data = n_data
    flag_modified(game, "npc_data")


# ============================================================
# 변환 헬퍼: DB Scenario → ScenarioAssets
# ============================================================

def _scenario_to_assets(scenario: Scenario) -> ScenarioAssets:
    """DB Scenario 모델 → ScenarioAssets 변환"""
    world_data = scenario.default_world_data or {}
    prompt_data = scenario.base_system_prompt or {}

    return ScenarioAssets(
        scenario_id=scenario.title,
        scenario=world_data.get("scenario", {}),
        story_graph=world_data.get("story_graph", {}),
        npcs=world_data.get("npcs", {}),
        items=world_data.get("items", {}),
        memory_rules=prompt_data.get("memory_rules", {}),
        extras=world_data.get("extras", {}),
    )


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


# ============================================================
# GameService
# ============================================================

class GameService:

    @classmethod
    def process_turn(
        cls,
        db: Session,
        game_id: int,
        input_data: Dict[str, Any],
        game: Games,
    ) -> TurnResult:
        """
        낮 파이프라인 실행:
        LockManager → DayController → EndingChecker → NarrativeLayer

        Args:
            db: SQLAlchemy 세션
            game_id: 게임 ID
            input_data: 유저 입력 {"chat_input": "...", ...}
            game: Games DB 인스턴스

        Returns:
            TurnResult: 파이프라인 실행 결과
        """
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

        # ── Step 8: WorldState → DB 반영 + 저장 ──
        _world_state_to_games(game, world_after)
        crud_game.update_game(db, game)

        logger.info(
            f"Turn completed: game={game_id}, "
            f"turn={world_after.turn}, ending={ending_result.reached}"
        )

        return TurnResult(
            narrative=narrative,
            ending_info=ending_info,
            state_delta=tool_result.state_delta,
            debug=debug,
        )

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

        world_obj = WorldDataSchema(**(game.world_data_snapshot or {}))
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
