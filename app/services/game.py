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

# 정의하신 스키마들 import
from app.schemas.llm_payload_input import (
    LLMInputPayload, 
    UserInputSchema, 
    WorldInfoSchema, 
    PlayerSchema as LLMPlayerSchema, 
    ItemCollectionSchema,
    LogicContextSchema, 
    ModelConfigSchema,
)
from app.schemas.client_sync import GameClientSyncSchema
from app.schemas.world_meta_data import WorldDataSchema
from app.schemas.npc_info import NpcCollectionSchema
from app.schemas.player_info import PlayerSchema
from app.schemas.llm_response_schema import LLMResponseSchema

# (가상의 LLM 호출 함수 import - 나중에 구현 필요)
# from app.services.llm_client import call_llm_api 


class GameService:
    @staticmethod
    def execute_turn_with_llm(game: Any, input_data: Dict[str, Any]) -> LLMInputPayload:
        """
        DB 데이터(game 객체)를 LLMInputPayload 스키마로 변환하여 반환합니다.
        이미지의 컬럼명(world_data_snapshot, player_data, npc_data)을 반영했습니다.
        
        Args:
            game: SQLAlchemy Game 모델 인스턴스
            input_data: 유저 입력 딕셔너리
            
        Returns:
            LLMInputPayload: Pydantic 객체
        """

        # ---------------------------------------------------------
        # 0. DB 데이터 접근 (이미지 기준 컬럼명 매핑)
        # ---------------------------------------------------------
        # DB 컬럼: world_data_snapshot (JSONB) - 메타, 아이템, 룰, 상태 등 포함
        snapshot = game.world_data_snapshot or {}
        
        # DB 컬럼: player_data (JSONB)
        raw_player_data = copy.deepcopy(game.player_data or {})
        
        # DB 컬럼: npc_data (JSONB)
        raw_npc_data = game.npc_data or {"npcs": []}


        # =========================================================
        # 1. [Arg 1] 유저 입력 (User Input)
        # =========================================================
        arg1 = UserInputSchema(
            chat_input=input_data.get("chat_input", ""),
            npc_name=input_data.get("npc_name"),
            item_name=input_data.get("item_name")
        )


        # =========================================================
        # 2. [Arg 2] 월드 정보 (World Info)
        # =========================================================
        
        # [Player] 'memo' 제거 및 'memory' 보장
        if "memo" in raw_player_data:
            del raw_player_data["memo"] # LLM에게 메모장은 보여주지 않음 (토큰 절약 & 역할 분리)
            
        player_obj = LLMPlayerSchema(
            current_node=raw_player_data.get("current_node", "start"),
            inventory=raw_player_data.get("inventory", []),
            memory=raw_player_data.get("memory", {}) # 없으면 빈 dict
        )

        # [NPC] DB 데이터 -> 스키마 변환
        # 이미지의 npc_data가 {"npcs": [...]} 형태라고 가정
        # 만약 {"family": {...}} 형태라면 변환 로직이 필요하지만, 
        # 최신 스키마(NpcCollectionSchema)를 따르신다면 이대로 OK
        npcs_obj = NpcCollectionSchema(**raw_npc_data)

        # [Items] Snapshot 안에 있는 items 가져오기
        # snapshot 구조: { "items": { "items": [...] }, ... }
        items_source = snapshot.get("items", {"items": []})
        items_obj = ItemCollectionSchema(**items_source)

        # Arg 2 래퍼 생성
        arg2 = WorldInfoSchema(
            player=player_obj,
            npcs=npcs_obj,
            items=items_obj
        )


        # =========================================================
        # 3. [Arg 3] 로직 컨텍스트 (Logic Context)
        # =========================================================
        
        # Snapshot에서 Meta, State, Rules 추출
        # 이미지의 world_data_snapshot 안에 'meta', 'state' 키가 보입니다.
        
        # 1) Snapshot 가져오기
        snapshot = game.world_data_snapshot or {}
        
        # 2) Scenario 데이터 접근 (여기에 Meta와 Rules가 다 들어있음!)
        scenario_data = snapshot.get("scenario", {}) 
        
        # 3) Meta 정보 추출 (scenario_data 내부에서 꺼내기)
        meta_info = {
            "title": scenario_data.get("title", ""),
            "genre": scenario_data.get("genre", ""),
            "tone": scenario_data.get("tone", ""),
            "pov": scenario_data.get("pov", ""),
        }
        
        # 4) Rules 정보 추출 (scenario_data 내부에서 꺼내기)
        rules_info = {
            "global_rules": scenario_data.get("global_rules", []),
            "victory_conditions": scenario_data.get("victory_conditions", []),
            "failure_conditions": scenario_data.get("failure_conditions", []),
            "endings": scenario_data.get("endings", [])
        }
    
        # 5) State 정보 (이건 최상위에 있는 게 맞음)
        state_info = snapshot.get("state", {})

        # 조립
        arg3 = LogicContextSchema(
            meta=meta_info,
            state=state_info, 
            rules=rules_info
        )


        # =========================================================
        # 4. [Arg 4] 모델 설정 (Model Config)
        # =========================================================
        # 필요시 DB나 환경변수에서 로드
        arg4 = ModelConfigSchema(
            model_name="gpt-4-turbo",
            temperature=0.7
        )


        # =========================================================
        # 👑 [최종] 페이로드 조립 및 반환
        # =========================================================
        payload = LLMInputPayload(
            arg1_user_input=arg1,
            arg2_world_info=arg2,
            arg3_logic_context=arg3,
            arg4_model_config=arg4
        )
        
        return payload



    @staticmethod
    def mock_llm_process(input_payload: dict) -> LLMResponseSchema:
        """
        [TODO: 실제 LLM 호출로 교체될 부분]
        지금은 무조건 고정된 가짜 데이터를 반환합니다.
        """
        
        # 입력받은 데이터에서 유저 질문을 확인(로그용)
        user_msg = input_payload["arg1_user_input"]["chat_input"]
        print(f"DEBUG: LLM received input: {user_msg}")

        # 가상의 LLM 응답 생성
        mock_response = LLMResponseSchema(
            response_text=f"([시스템] 가짜 응답입니다) 당신은 '{user_msg}'라고 말했습니다. NPC가 흥미를 보입니다.",
            
            # 변수 업데이트 테스트: 신뢰도 +5
            update_vars={"trust": 5, "clue_count": 1},
            
            # 아이템 획득 테스트
            items_to_add=[""],
            
            # 메모 추가 테스트
            new_memo="NPC와의 대화에서 수상한 점을 발견함.",
            
            # 다음 노드 (없으면 None)
            next_node=None 
        )
        
        return mock_response

    @staticmethod
    def apply_llm_response_to_game(game, response: LLMResponseSchema):
        """
        LLM 응답(response)을 게임 객체(game)에 반영합니다.
        #TODO 일단은 이대로 갈 지 안갈지 모르기 때문에 이대로 둡시다
        """
        
        # =================================================
        # 1. World State 업데이트 (Vars, Flags, Turn)
        # =================================================
        # DB에서 가져오기 (없으면 빈 딕셔너리)
        snapshot = dict(game.world_data_snapshot or {})
        state = snapshot.get("state", {})
        
        # (1) Vars 병합 (기존 값 + 변동 값 / 혹은 덮어쓰기 로직)
        # 여기서는 단순 덮어쓰기/추가 로직으로 구현 (기획에 따라 += 가능)
        current_vars = state.get("vars", {})
        current_vars.update(response.update_vars) # 딕셔너리 병합
        state["vars"] = current_vars

        # (2) Flags 병합
        current_flags = state.get("flags", {})
        current_flags.update(response.update_flags)
        state["flags"] = current_flags
        
        # (3) 턴 증가 (대화 한 번당 1턴 소모라고 가정 시)
        # current_turn = state.get("turn", 1)
        # state["turn"] = current_turn + 1
        
        # 다시 할당 (JSONB 변경 감지용)
        snapshot["state"] = state
        game.world_data_snapshot = snapshot


        # =================================================
        # 2. Player Data 업데이트 (Inventory, Memo, Node)
        # =================================================
        p_data = dict(game.player_data or {})
        
        # (1) 아이템 추가
        inventory = set(p_data.get("inventory", [])) # 중복 방지 set
        for item in response.items_to_add:
            inventory.add(item)
        for item in response.items_to_remove:
            if item in inventory:
                inventory.remove(item)
        p_data["inventory"] = list(inventory)
        
        # (2) 메모 추가
        if response.new_memo:
            memos = p_data.get("memo", [])
            # 간단하게 문자열 리스트로 관리하거나, PlayerMemoSchema 구조를 따를 수도 있음
            # 여기서는 간단히 텍스트 추가로 예시
            new_id = len(memos) + 1
            memos.append({"id": new_id, "text": response.new_memo, "created_at_turn": state.get("turn", 0)})
            p_data["memo"] = memos

        # (3) 노드 이동 (씬 변경)
        if response.next_node:
            p_data["current_node"] = response.next_node

        # (4) LLM 기억(Memory) 업데이트
        current_memory = p_data.get("memory", {})
        current_memory.update(response.update_memory)
        p_data["memory"] = current_memory

        # 다시 할당
        game.player_data = p_data
        
        return game


    @classmethod
    def process_turn(cls, db: Session, game_id: int, input_data: dict, game: dict) -> dict:
        """
        1. DB에서 게임 데이터를 가져와 LLM용 컨텍스트(Prompt)를 구성합니다.
        2. LLM에게 요청을 보냅니다.
        3. LLM의 응답(JSON)을 파싱하여 반환합니다.
        """
        
        # 1. LLM용 컨텍스트 구성
        input_dict = cls.execute_turn_with_llm(game, input_data)

        # 2. input dict를 llm에서 처리해서 반환
        # TODO : 실제 LLM 호출 로직으로 교체 필요
        llm_response_obj = cls.mock_llm_process(input_dict.dict())


        # 3. 수정된 내용을 적용
        cls.apply_llm_response_to_game(game, llm_response_obj)

        # 4. 저장 및 결과 반환
        crud_game.update_game(db, game)
        
        return input_dict

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
        world_obj = WorldDataSchema(**(game.world_data_snapshot or {}))

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
        
        # 4. 최종 통합 스키마 생성
        client_sync_data = GameClientSyncSchema(
            world=world_obj,
            player=player_obj,
            npcs=npcs_obj
        )

        return client_sync_data