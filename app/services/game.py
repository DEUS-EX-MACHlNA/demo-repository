from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.db_models.scenario import Scenario
from app.db_models.game import Games
import json
import copy
import copy
from sqlalchemy.orm import Session
from app.db_models.game import Games
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

from sqlalchemy.orm.attributes import flag_modified


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
    def process_turn(cls, db: Session, game_id: int, input_data: dict, game: Games) -> dict:
        """
        필요한 인자
        1. 유저 입력
        2. game state data
        3. 시나리오 에셋
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






        # 4. DayController 실행
        controller = get_day_controller()
        
        # User Input 문자열 추출
        user_msg = input_data.get("chat_input", "")
        # NPC Name, Item Name 등이 있다면 user_input 전처리가 필요할 수 있음
        # 일단은 chat_input을 그대로 전달
        
        tool_result = controller.process(
            user_input=user_msg,
            world_state=world_state,
            assets=assets
        )

        
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

        # 5. 결과 반영 (apply_chat_result가 ToolResult 객체 처리하도록 수정됨)
        
        #cls.apply_chat_result(game, tool_result)
        cls.apply_chat_result(game, mock_day_controller_result)

        # [VERIFICATION] API 호출 시 바로 테스트 결과 확인
        print("\n=== [GameService] Apply Result Verification ===")
        print(f"Turn: {game.world_meta_data.get('state', {}).get('turn')} (Expected: incremented)")
        print(f"Inventory: {game.player_data.get('inventory')}")
        print(f"Memory: {game.player_data.get('memory')}")
        print("===============================================\n")

        # 6. 저장
        crud_game.update_game(db, game)

        #return tool_result.__dict__ # Dict 반환
        return mock_day_controller_result.__dict__

    # 게임 id를 받아서 진행된 게임을 불러오기
    @staticmethod
    def start_game(db: Session, game_id: int) -> GameClientSyncSchema:
        """
        게임 id를 받아서 진행된 게임을 불러와서
        GameClientSyncSchema 형식으로 반환합니다.
        """
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

        # 3. NPC Data
        # DB에 저장된 npc_data를 NpcCollectionSchema로 변환
        npc_data = copy.deepcopy(game.npc_data) or {"npcs": []}
                    
        npcs_obj = NpcCollectionSchema(**npc_data)

        # [DEBUG] npcs_obj 내부 확인
        print(f"DEBUG: NpcCollectionSchema created. Count: {len(npcs_obj.npcs)}")
        if npcs_obj.npcs:
            first_npc = npcs_obj.npcs[0]
            # Pydantic v1: .dict(), v2: .model_dump()
            try:
                 print(f"DEBUG: First NPC dump: {first_npc.dict()}")
            except:
                 print(f"DEBUG: First NPC str: {str(first_npc)}")
        
        client_sync_data = GameClientSyncSchema(
            world=world_obj,
            player=player_obj,
            npcs=npcs_obj
        )

        try:
            # 5. Redis에 캐싱 (Key: game:{game_id})
            redis_client = get_redis_client()
            redis_key = f"game:{game_id}"
            
            # Pydantic 모델을 JSON 문자열로 변환하여 저장
            # 1시간(3600초) 만료 시간 설정
            redis_client.setex(redis_key, 3600, client_sync_data.json())
            print(f"DEBUG: Game state cached in Redis. Key: {redis_key}")
        except Exception as e:
            # Redis 연결 실패 등 예외 발생 시 로그만 찍고 진행
            print(f"ERROR: Failed to cache game state in Redis. Error: {e}")

        return client_sync_data