from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base
from app.schemas.status import ChatAt

class ChatLogs(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    
    turn_number = Column(Integer, nullable=False, default=1)
    chat_at = Column(SQLEnum(ChatAt), nullable=False, default=ChatAt.DAY)


    user_input = Column(Text, nullable=True) # 사용자가 말한거
    ai_output = Column(Text, nullable=True)  # AI가 답한거
    
    # 생성 시간
    create_time = Column(DateTime, server_default=func.now())
    
    # 이전 상태 백업본 (JSONB) - 추후 구현 예정, 현재는 빈 dict
    prev_state_snapshot = Column(JSONB, nullable=False, default={})

    # Relationship
    game = relationship("Games", backref="chat_logs")
