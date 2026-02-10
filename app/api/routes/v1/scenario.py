from app.schemas import GameClientSyncSchema, GameResponse
from app.loader import get_loader
from app.services.scenario import ScenarioService
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.db_models.game import Games, GameStatus
from app.db_models.scenario import Scenario
from app.config import SCENARIOS_BASE_PATH


router = APIRouter(tags=["scenario"])


@router.get("/", summary="사용 가능한 시나리오 목록")
def list_scenarios() -> dict:
    """사용 가능한 모든 시나리오 목록 반환"""
    loader = get_loader(SCENARIOS_BASE_PATH)
    scenarios = loader.list_scenarios()
    return {"scenarios": scenarios}


#해당 시나리오로 시작

@router.get("/start/{scenario_id}", summary="시나리오 시작")
def start_scenario(scenario_id: int, user_id: int) -> GameClientSyncSchema:
    """시나리오 시작"""
    game = ScenarioService.create_game(scenario_id, user_id)
    return game
