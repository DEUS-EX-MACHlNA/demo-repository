"""
init_db.py
데이터베이스 초기화 스크립트
"""
import os
from dotenv import load_dotenv
from app.database import init_db, drop_db

# .env 파일 로드
load_dotenv()

# 모든 모델을 먼저 import해서 Base.metadata에 등록
from app.db_models import Scenario, Games, GameStatus, ChatLogs  # noqa: F401
from app.database import init_db, drop_db

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        print("DB를 리셋합니다...")
        drop_db()
        init_db()
    else:
        print("DB를 초기화합니다...")
        init_db()
