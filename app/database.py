"""
app/database.py
SQLAlchemy ORM 설정 및 DB 연결 관리
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from typing import Generator

# .env 파일 로드
load_dotenv()

# 환경 변수에서 DB 연결 정보 읽기
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "1557")
DB_NAME = os.getenv("DB_NAME", "maratang_db")

# PostgreSQL 연결 문자열
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# SQLAlchemy 엔진 생성
engine = create_engine(
    DATABASE_URL,
    echo=False,  # 디버깅을 위해 True로 변경 가능
    pool_pre_ping=True,  # 연결 유효성 검사
)

# 세션 팩토리
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base 클래스 (모든 ORM 모델이 상속)
Base = declarative_base()


def get_db() -> Generator:
    """
    의존성 주입용 DB 세션 생성 함수
    FastAPI와 함께 사용할 경우:
        from fastapi import Depends
        async def some_endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    DB 초기화 - 모든 테이블 생성
    """
    Base.metadata.create_all(bind=engine)
    print(f"✓ Database initialized: {DATABASE_URL}")


def drop_db():
    """
    DB 초기화 제거 - 모든 테이블 삭제 (테스트용)
    """
    Base.metadata.drop_all(bind=engine)
    print(f"✓ Database dropped: {DATABASE_URL}")
