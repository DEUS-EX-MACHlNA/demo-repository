from sqlalchemy.orm import Session
from typing import Optional
from app.db_models.game import Games

def get_game_by_id(db: Session, game_id: int) -> Optional[Games]:
    """Game ID로 게임 정보를 조회합니다."""
    return db.query(Games).filter(Games.id == game_id).first()

def create_game(db: Session, game: Games) -> Games:
    """새로운 게임을 생성하고 DB에 저장합니다."""
    db.add(game)
    db.commit()
    db.refresh(game)
    return game

def update_game(db: Session, game: Games) -> Games:
    """게임 정보를 업데이트하고 DB에 저장합니다."""
    db.add(game)
    db.commit()
    db.refresh(game)
    return game
