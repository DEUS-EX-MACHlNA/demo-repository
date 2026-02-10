from sqlalchemy.orm import Session
from app.db_models.chat_log import ChatLogs
from app.schemas.status import ChatAt
from typing import Optional, Dict

def create_chat_log(
    db: Session,
    game_id: int,
    user_input: Optional[str],
    ai_output: Optional[str],
    turn_number: int,
    prev_state_snapshot: Dict,
    chat_at: ChatAt = ChatAt.DAY
) -> ChatLogs:
    """
    ChatLog 생성 및 저장
    """
    db_obj = ChatLogs(
        game_id=game_id,
        user_input=user_input,
        ai_output=ai_output,
        turn_number=turn_number,
        prev_state_snapshot=prev_state_snapshot,
        chat_at=chat_at
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj
