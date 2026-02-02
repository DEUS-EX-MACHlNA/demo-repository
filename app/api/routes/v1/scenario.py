from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.db_models.game import Games, GameStatus
from app.db_models.scenario import Scenario  


router = APIRouter(tags=["scenario"])