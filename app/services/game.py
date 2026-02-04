from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.db_models.scenario import Scenario
from app.db_models.game import Games, GameStatus

"""
진행방식

1. 일단 파싱해
2. 그리고 해당 게임의 정보를 불라와 -> 이는 redis에서 바뀜
3. 그리고 인자의 요구에 맞게 재조합시켜
4. 이제 그걸 redis에 넣어두고 그걸 꺼내봅시다
"""


import json
import copy
from sqlalchemy.orm import Session
from app.db_models.game import Games

# (가상의 LLM 호출 함수 import - 나중에 구현 필요)
# from app.services.llm_client import call_llm_api 


def execute_turn_with_llm(game: dict, input_data: dict) -> dict:
    """
    DB 데이터를 4가지 핵심 인자로 가공하여 외부 LLM 함수를 실행합니다.
    """
    

    arg1_user_input = input_data

    # =========================================================
    # Argument 2. 월드의 정보 (World Info)
    # 구성: Player(메모 제외, memory 추가) + NPC(정보+기억) + Items(정의)
    # =========================================================
    
    # [Player] DB 원본 보호를 위해 deepcopy 사용
    player_context = copy.deepcopy(game.player_data)
    
    # 1) 'memo' 제거
    if "memo" in player_context:
        del player_context["memo"]
        
    # 2) 'memory' dict 추가 (요청하신 대로 빈 dict 혹은 기존 데이터 활용)
    # (기존 player_data에 memory가 없다면 빈 dict로 초기화)
    player_context["memory"] = player_context.get("memory", {})

    # [NPC] 전체 데이터 (stats, memory 포함)
    npc_context = copy.deepcopy(game.npc_data)

    # [Items] Snapshot의 definitions -> items 블럭 가져오기
    # items는 {id: {data...}} 형태의 딕셔너리임
    items_context = game.world_data_snapshot.get("definitions", {}).get("items", {})

    arg2_world_info = {
        "player": player_context,
        "npcs":npc_context,
        "items": items_context
    }


    # =========================================================
    # Argument 3. 분기 및 규칙 정보 (Logic Context)
    # 구성: Meta + State + Rules
    # =========================================================
    snapshot = game.world_data_snapshot
    
    arg3_logic_context = {
        "meta": snapshot.get("meta", {}),   # 장르, 절대 규칙 등
        "state": snapshot.get("state", {}), # 턴, 변수(vars), 플래그
        "rules": snapshot.get("rules", {})  # 승리/패배 조건, 엔딩 정의
    }


    # =========================================================
    # Argument 4. 필요한 LLM 모델 (Model Config)
    # =========================================================
    # 추후 추가 예정이므로 비어있는 dict로 설정
    arg4_model_config = {
        # "model_name": "gpt-4-turbo",
        # "temperature": 0.7
    }

    # =========================================================
    # [최종] 외부 함수 실행
    # =========================================================
    # result = call_external_llm(
    #     user_input=arg1_user_input,
    #     world_info=arg2_world_info,
    #     logic_context=arg3_logic_context,
    #     model_config=arg4_model_config
    # )

    # return result

    return {
        "arg1_user_input": arg1_user_input,
        "arg2_world_info": arg2_world_info,
        "arg3_logic_context": arg3_logic_context,
        "arg4_model_config": arg4_model_config
    }



def transform_game_state(db: Session, game_id: int, input_data: dict, game: dict) -> dict:
    """
    1. DB에서 게임 데이터를 가져와 LLM용 컨텍스트(Prompt)를 구성합니다.
    2. LLM에게 요청을 보냅니다.
    3. LLM의 응답(JSON)을 파싱하여 반환합니다.
    """
    
    # 1. LLM용 컨텍스트 구성
    input_dict = execute_turn_with_llm(game, input_data)

    # 2. input dict를 llm에서 처리해서 반환
    # TODO : 실제 LLM 호출 로직으로 교체 필요

    #일단 Input_dict와 양식은 같지만 내용은 다른 output_dict를 반환
    output_dict = copy.deepcopy(input_dict)
    output_dict["arg1_user_input"] = {
        "chat_input": "이것은 LLM에서 처리된 응답입니다.",
        "npc_name": input_data.get("npc_name"),
        "item_name": input_data.get("item_name")
    }

    # 3. 수정된 내용을 적용



    

    return input_dict