# 이는 추후에 gameService로 바뀔 예정입니다
# 일단 테스트용으로 간략하게 만들 예정이라 repository도 여기에 넣어 둘 생각입니다

# 1. 일단 요청 받은 id를 기준으로 scenario 데이터를 DB에서 가져옵니다

from __future__ import annotations
import sys
from pathlib import Path
from typing import Union

# 프로젝트 루트를 sys.path에 추가 (직접 실행 시 'app' 패키지 import 문제 해결)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
	sys.path.insert(0, str(project_root))

from app.database import SessionLocal
from app.db_models.scenario import Scenario
from app.db_models.game import Games, GameStatus
from app.schemas.npc_info import NpcSchema, NpcCollectionSchema
from app.schemas.player_info import PlayerSchema, PlayerMemoSchema
from app.schemas.world_meta_data import (
    WorldDataSchema,
    ScenarioSchema,
    ItemsCollectionSchema,
    LockSchema,
    LocksSchemaList,
    CurrentStateSchema,
    ScenarioSchema,
    EndingSchema,
    )
from app.schemas.item_info import ItemSchema
from app.schemas.status import ItemStatus
import json
import copy
from typing import Dict, Any
from app.crud import scenario as crud_scenario
from app.crud import game as crud_game
from app.schemas.client_sync import GameClientSyncSchema
from app.services.game import _scenario_to_assets


class ScenarioService:
    @staticmethod
    def extract_initial_npc_data(world_data: Dict[str, Any]) -> dict:
        """
        world_data(JSON)에서 NPC 데이터를 추출하여 
        NpcCollectionSchema 규격에 맞는 딕셔너리 형태로 변환합니다.
        """
        
        # 1. 원본 데이터 가져오기 (없으면 빈 리스트)
        source_npcs = world_data.get("npcs", {}).get("npcs", [])
        
        valid_npc_list = []
        
        for npc_data in source_npcs:
            # 2. Pydantic 스키마로 데이터 매핑 및 검증
            # - 스키마에 없는 필드(current_node 등)는 자동으로 걸러집니다.
            # - 필수 필드(npc_id, name 등)가 없으면 여기서 에러가 발생해 안전합니다.
            
            npc_obj = NpcSchema(
                npc_id=npc_data["npc_id"],
                name=npc_data["name"],
                role=npc_data["role"],
                user_id=npc_data.get("user_id"), # 템플릿 스트링("{user_id}")이거나 None
                
                # stats: JSON에 있는 그대로 가져오되, 없으면 빈 dict
                stats=npc_data.get("stats", {}),
                
                # persona: JSON에 있는 그대로 가져오기
                persona=npc_data.get("persona", {}),
                
                #npc 현재 위치(있으면 넣고 없으면 기본값)
                current_node=npc_data.get("current_node", ""),
                
                # memory: 초기 상태니 빈 dict로 시작
                memory=[]
            )
            
            valid_npc_list.append(npc_obj)

        # 3. Collection 스키마로 감싸기
        # 구조: { "npcs": [ NpcSchema(...), NpcSchema(...) ] }
        collection = NpcCollectionSchema(npcs=valid_npc_list)
        
        # 4. DB(JSONB) 저장을 위해 딕셔너리로 변환하여 반환
        return collection.dict()

    @staticmethod
    def extract_initial_player_data(world_data: Dict[str, Any]) -> dict:
        """
        Scenario 데이터(world_data)를 기반으로 
        PlayerSchema 규격에 맞는 초기 플레이어 데이터를 생성합니다.
        """
        
        # 1. 시나리오 데이터와 아이템 소스 안전하게 가져오기
        scenario_meta = world_data.get("scenario", {})
        items_source = world_data.get("items", {}).get("items", [])
        
        # [1] 시작 위치 (current_node)
        start_node = scenario_meta.get("opening_scene_id", "act1_open")
        
        # [2] 초기 인벤토리 (inventory)
        # 💡 요청하신 부분: 전체 객체가 아니라 'item_id' 문자열만 추출합니다.
        start_inventory = [
            item["item_id"]
            for item in items_source
            if item.get("acquire", {}).get("method") == "start"
        ]
        
        # [3] 초기 메모 (memo)
        initial_memos = []
        raw_memos = scenario_meta.get("initial_memos", [])
        
        for idx, memo_text in enumerate(raw_memos, 1):
            initial_memos.append(
                PlayerMemoSchema(
                    id=idx,
                    text=memo_text,
                    created_at_turn=0
                )
            )

        # [4] PlayerSchema 객체 생성
        # memory는 빈 딕셔너리로 초기화
        player_data = PlayerSchema(
            current_node=start_node,
            inventory=start_inventory, # -> ["item_id_1", "item_id_2"] 형태
            memo=initial_memos,
            stats={"humanity": 100},  # 기본 스탯 설정
            memory=[]
        )
        
        # [5] 딕셔너리로 변환하여 반환 (DB 저장용)
        return player_data.dict()

    @staticmethod
    def extract_initial_world_data(world_data: Dict[str, Any]) -> dict:
        """
        Scenario 원본 데이터(world_data)를 기반으로
        WorldDataSchema 규격에 맞는 초기 월드 데이터를 생성합니다.
        
        Args:
            world_data: scenario.default_world_data (JSONB)
        
        Returns:
            dict: WorldDataSchema.dict() 형태 (DB 저장용)
        """
        
        # 1. 원본 데이터 안전하게 접근
        scenario_meta = world_data.get("scenario", {})
        state_schema = scenario_meta.get("state_schema", {})
        source_items = world_data.get("items", {}).get("items", [])
        source_locks = world_data.get("extras", {}).get("locks", {}).get("locks", [])
        source_locks = world_data.get("extras", {}).get("locks", {}).get("locks", [])
        # source_nodes removed

        # =========================================================
        # 1. [Scenario] 시나리오 메타 및 규칙 (Static)
        # =========================================================
        
        # Endings 리스트 변환
        endings_list = []
        for end in scenario_meta.get("endings", []):
            endings_list.append(EndingSchema(
                ending_id=end["ending_id"],
                name=end["name"],
                epilogue_prompt=end["epilogue_prompt"],
                condition=end["condition"],
                on_enter_events=end.get("on_enter_events", [])
            ))

        scenario_obj = ScenarioSchema(
            global_rules=scenario_meta.get("global_rules", []),
            victory_conditions=scenario_meta.get("victory_conditions", []),
            failure_conditions=scenario_meta.get("failure_conditions", []),
            endings=endings_list,
            # state_schema는 제외됨
        )

        # [Story Graph] 제거됨 (Static Data 분리)

        # =========================================================
        # 3. [Items] 아이템 도감 (Static)
        # =========================================================
        
        items_list = []
        for item in source_items:
            # 초기 상태 결정: 'start'로 획득하는 아이템은 ACQUIRED 상태
            initial_state = ItemStatus.NOT_ACQUIRED
            if item.get("acquire", {}).get("method") == "start":
                initial_state = ItemStatus.ACQUIRED

            items_list.append(ItemSchema(
                item_id=item["item_id"],
                name=item["name"],
                type=item["type"],
                description=item["description"],
                acquire=item["acquire"],
                use=item["use"],
                state=item.get("state", initial_state),
                location=item.get("location", "")
            ))
            
        items_obj = ItemsCollectionSchema(items=items_list)

        # =========================================================
        # 4. [Locks] 잠금 정보 (Static)
        #    - 전개형(Flattened) 스키마 적용
        # =========================================================
        
        locks_list = []
        for lock in source_locks:
            locks_list.append(LockSchema(
                info_id=lock["info_id"],
                info_title=lock["info_title"],
                description=lock["description"],
                is_unlocked=False, # 초기 상태는 항상 잠금
                linked_info_id=lock.get("linked_info_id"),
                unlock_condition=lock.get("unlock_condition"),
                reveal_trigger=lock.get("reveal_trigger"),
                access=lock.get("access", {})
            ))
            
        locks_obj = LocksSchemaList(locks=locks_list)

        # =========================================================
        # 5. [State] 초기 동적 상태 (Dynamic)
        # =========================================================
        
        # (1) Vars 초기화
        initial_vars = {}
        if "vars" in state_schema:
            for key, spec in state_schema["vars"].items():
                initial_vars[key] = spec.get("default", 0)
                
        # (2) Flags 초기화
        initial_flags = {}
        if "flags" in state_schema:
            for key, spec in state_schema["flags"].items():
                initial_flags[key] = spec.get("default", None)
        
        # [중요] 초기화 플래그 강제 설정
        initial_flags["act"] = 1
        
        # (3) Current State 생성
        current_state_obj = CurrentStateSchema(
            turn=state_schema.get("system", {}).get("turn", {}).get("default", 1),
            date=state_schema.get("system", {}).get("date", {}).get("default", 1),
            vars=initial_vars,
            flags=initial_flags,
            # active_events=[] # 삭제됨
        )

        # =========================================================
        # 6. 최종 조립 및 반환 (Pydantic 검증 완료)
        # =========================================================
        
        full_world_data = WorldDataSchema(
            state=current_state_obj,
            scenario=scenario_obj,
            # story_graph=story_graph_obj, # 제거됨
            locks=locks_obj,
            items=items_obj
        )
        
        # DB 저장을 위해 dict로 변환
        return full_world_data.dict()


    @staticmethod
    def get_json(scenario_id: int) -> dict:
        """
        주어진 시나리오 식별자에 대해 DB에서 `base_system_prompt`와
        `default_world_data`를 반환합니다.

        Args:
            scenario_id: 정수형 PK(id) 또는 시나리오 문자열 식별자(title)

        Returns:
            dict: {"base_system_prompt": ..., "default_world_data": ...}

        Raises:
            ValueError: 해당 시나리오를 찾을 수 없을 때
        """
        db = SessionLocal()
        try:
            # 정수면 PK로 조회, 아니면 title로 조회
            if isinstance(scenario_id, int):
                scenario = crud_scenario.get_scenario_by_id(db, scenario_id)
            if not scenario:
                raise ValueError(f"Scenario not found: {scenario_id}")
            return {
                "base_system_prompt": scenario.base_system_prompt,
                "default_world_data": scenario.default_world_data,
            }
        finally:
            db.close()

    # 여기가 본진
    @classmethod
    def create_game(cls, scenario_id: int, user_id: int = 1) -> GameClientSyncSchema:
        """
        주어진 시나리오 ID로 새로운 게임 레코드를 생성합니다.
        `npc_data`는 `default_world_data`에서 자동으로 추출됩니다.
        나머지 필드(`player_data`, `summary`)는 추후 단계별로 채워질 예정입니다.

        Args:
            scenario_id: 생성할 게임과 연결할 시나리오의 PK
            user_id: 게임을 생성한 사용자 ID (기본값 1)

        Raises:
            ValueError: 지정한 시나리오가 존재하지 않을 때
        """
        db = SessionLocal()
        try:
            scenario = crud_scenario.get_scenario_by_id(db, scenario_id)
            if not scenario:
                raise ValueError(f"Scenario not found: {scenario_id}")

            # default_world_data에서 데이터 추출
            default_world = scenario.world_asset_data or {}
            
            # 클래스 메서드로 변경됨에 따라 cls.메서드 호출
            npc_data = cls.extract_initial_npc_data(default_world)
            player_data = cls.extract_initial_player_data(default_world)
            world_state_data = cls.extract_initial_world_data(default_world)

            game = Games(
                scenarios_id=scenario.id,
                user_id=user_id,
                world_meta_data=world_state_data,
                player_data=player_data,
                npc_data=npc_data,
                summary={},  # TODO: 이 부분은 추후 LLM에 넣어 둘 내용을 의미
                status=GameStatus.LIVE,
            )
        
            crud_game.create_game(db, game)
            
            return GameClientSyncSchema(
                game_id=game.id,
                user_id=user_id,
            )
        finally:
            db.close()
