from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Integer, func, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base
from app.schemas.status import GameStatus

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
from datetime import datetime


# ============================================================
# SQLAlchemy ORM Games Model
# ============================================================
class Games(Base):
    __tablename__ = "games"

    # ERD와 정확히 일치하는 컬럼 정의
    id = Column(Integer, primary_key=True, index=True)
    
    # FK: Scenarios 테이블과의 관계 (일대다: Scenario는 일, Games는 다)
    scenarios_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
    
    # FK: Users 테이블과의 관계 (임시로 정수 ID만 저장)
    user_id = Column(Integer, nullable=False, default=1)
    
    # ERD: 게임 진행 중 현재 세계관 스냅샷
    world_data_snapshot = Column(JSONB, nullable=False, default={})
    
    # ERD: 플레이어 데이터 (인벤토리, 상태 등)
    player_data = Column(JSONB, nullable=False, default={})
    
    # ERD: NPC 정보 (신뢰도, 경계심 등)
    npc_data = Column(JSONB, nullable=False, default={})
    
    # ERD: 게임 요약본
    summary = Column(JSONB, nullable=False, default={})
    
    # ERD: 게임 상태 (live, ending)
    status = Column(SQLEnum(GameStatus), nullable=False, default=GameStatus.LIVE)
    
    # 시간 정보
    create_time = Column(DateTime, server_default=func.now())
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationship
    scenario = relationship("Scenario", backref="games")
