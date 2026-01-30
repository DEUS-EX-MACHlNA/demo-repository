from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
from datetime import datetime



# ============================================================
# SQLAlchemy ORM Scenario Model
# 나중에는 아래 요소들을 디렉토리로 분리할 수도 있음
# ============================================================
class Scenario(Base):
    __tablename__ = "scenarios"

    # ERD와 정확히 일치하는 컬럼 정의
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    
    # ERD: AI에게 주입할 기본 데이터
    base_system_prompt = Column(JSONB, nullable=False, default={}) 
    
    # ERD: 해당 게임 세계관의 메타데이터 (NPC, Item, Story 원본)
    default_world_data = Column(JSONB, nullable=False, default={})
    
    create_time = Column(DateTime, server_default=func.now())
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now())
