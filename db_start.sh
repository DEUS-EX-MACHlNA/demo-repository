# 주의! 이거 실행할대마다 DB가 드롭됩니다
# 나중에 데모가 아닌 메인에서는 DB는 유지할겁니다
# 난 분명 주의 드렸습니다 ㅎㅎ

# 1. 의존성 설치
pip install -r requirements.txt

# 2. .env 파일 생성 (.env.example 참고)
cp .env.example .env

# 3. PostgreSQL 시작 (Docker)
docker-compose up -d

# 4. DB 초기화
python init_db.py

# 5. DB 리셋 (테스트할 때)
python init_db.py reset