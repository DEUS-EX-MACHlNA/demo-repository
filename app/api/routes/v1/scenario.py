from app.loader import get_loader
from app.services.scenario import create_game_for_scenario
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.db_models.game import Games, GameStatus
from app.db_models.scenario import Scenario  
from app.config import SCENARIOS_BASE_PATH


router = APIRouter(tags=["scenario"])

# 출력 테스팅용 스키마
from typing import Dict, Any, Optional
from pydantic import BaseModel

class GameResponse(BaseModel):
    id: int
    user_id: int  # DB 모델이 String이면 str, Integer면 int로 맞춰주세요
    scenarios_id: int
    # DB에 값이 없을 수도 있다면 Optional 처리 추천
    world_state: Optional[Dict[str, Any]] = None
    player_state: Optional[Dict[str, Any]] = None
    npc_state: Optional[Dict[str, Any]] = None

    # 👇 [수정 포인트] Pydantic V1용 ORM 설정
    class Config:
        orm_mode = True

@router.get("/", summary="사용 가능한 시나리오 목록")
def list_scenarios() -> dict:
    """사용 가능한 모든 시나리오 목록 반환"""
    loader = get_loader(SCENARIOS_BASE_PATH)
    scenarios = loader.list_scenarios()
    return {"scenarios": scenarios}


#해당 시나리오로 시작

@router.get("/start/{scenario_id}", summary="시나리오 시작")
def start_scenario(scenario_id: int, user_id: int) -> int:
    """시나리오 시작"""
    game = create_game_for_scenario(scenario_id, user_id)
    return game