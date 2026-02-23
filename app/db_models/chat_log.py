from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base
from app.schemas.status import LogType

class ChatLogs(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    
    turn_number = Column(Integer, nullable=False, default=1)

    type = Column(SQLEnum(LogType), nullable=False)
    speaker = Column(String, nullable=False)
    # 화면에 표시될 텍스트
    content = Column(Text, nullable=False)
    
    # 생성 시간
    create_time = Column(DateTime, server_default=func.now())
    
    # 메타데이터 (JSONB) -> 밤의 대화는 여기에 표시시킬 예정
    metadata_ = Column("metadata", JSONB, nullable=False, default={})

    # Relationship
    game = relationship("Games", backref="chat_logs")
