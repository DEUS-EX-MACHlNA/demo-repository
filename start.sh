# 1. 의존성 설치
pip install -r requirements.txt

# # 2. .env 파일 생성 (.env.example 참고)
# cp .env.example .env

# 3. PostgreSQL 시작 (Docker)
docker-compose up -d

# 4. DB 초기화 (기본: 리셋 모드)
# DB를 날리고 새로 만듭니다. 데이타 유지가 필요하면 주석 처리하고 그 위의걸 주석 풀고 실행하세요
python init_db.py
#python init_db.py reset

# 5. DB 리셋 없이 실행 (데이터 유지) - 위 4번을 주석 처리하고 아래를 사용하세요.
# echo "Skipping DB Reset (Keep Data)..."

# 6. 시나리오 데이터 로드
python -m app.loader

# 7. 서버 실행 (옵션)
python -m app.main