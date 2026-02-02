
# 여기는 특정 시나리오로 실행하게 되면 DB에 접근해서 게임을 실행시켜 달라는 api를 호출하는 곳입니다.
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.db_models.game import Games, GameStatus
from app.db_models.scenario import Scenario  


router = APIRouter(tags=["game"])