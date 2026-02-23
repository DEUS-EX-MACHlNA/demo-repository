# 1. 의존성 설치
/opt/anaconda3/envs/maratang_env/bin/pip install -r requirements.txt

# # 2. .env 파일 생성 (.env.example 참고)
# cp .env.example .env

# 3. PostgreSQL 시작 (Docker)
docker-compose up -d

# 4. DB 초기화 (데이터 보존 + 마이그레이션)
# 기본 테이블 생성 (없는 경우)
/opt/anaconda3/envs/maratang_env/bin/python init_db.py
# 마이그레이션 적용 (변경 사항 반영)
/opt/anaconda3/envs/maratang_env/bin/alembic upgrade head

# 5. DB 리셋 없이 실행 (데이터 유지) - 위 4번을 주석 처리하고 아래를 사용하세요.
# echo "Skipping DB Reset (Keep Data)..."

# 6. 시나리오 데이터 로드
/opt/anaconda3/envs/maratang_env/bin/python -m app.loader

# 7. 서버 실행 (옵션)
/opt/anaconda3/envs/maratang_env/bin/python -m app.main