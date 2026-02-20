from sqlalchemy.orm import Session
from app.db_models.chat_log import ChatLogs
from app.schemas.status import LogType
from typing import Optional, Dict

def create_chat_log(
    db: Session,
    game_id: int,
    type: LogType,
    speaker: str,
    content: str,
    turn_number: int,
    metadata_: Dict = {},
) -> ChatLogs:
    """
    ChatLog 생성 및 저장
    """
    db_obj = ChatLogs(
        game_id=game_id,
        type=type,
        speaker=speaker,
        content=content,
        turn_number=turn_number,
        metadata_=metadata_
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

def get_chat_logs_by_game_id(db: Session, game_id: int) -> list[ChatLogs]:
    """
    특정 게임의 모든 챗 로그를 ID 순서(생성된 순서)대로 조회
    """
    return db.query(ChatLogs).filter(ChatLogs.game_id == game_id).order_by(ChatLogs.id).all()
