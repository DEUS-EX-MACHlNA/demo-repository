# 🎪 Maratang Game Server (마라탕 게임 서버)

Maratang은 생존 추리 스릴러 방탈출 게임을 위한 텍스트/LLM 기반 인터랙티브 백엔드 게임 서버입니다. 
AI(LLM) 기반의 시나리오 진행, NPC 상호작용, 인벤토리 관리 및 조사(추리) 시스템을 제공합니다.

## ✨ 주요 특징 (Features)
- 🤖 **LLM NPC 시스템**: `vLLM` (Kanana-8B 모델) 기반으로 사용자의 입력에 반응하는 지능형 NPC와 스토리 나레이터 구현
- 🌍 **상태 머신 시스템**: 턴제 기반 게임 진행, 플레이어 이동, 아이템 습득/사용, 기믹 해독 처리
- ⚡ **Redis 기반 고속 상태 관리**: 동시 접속자 처리 및 빠른 턴 진행을 위한 인메모리 게임 데이터 캐싱 (`O(1)` 속도로 게임 상태 읽기/쓰기 지원)
- 📊 **PostgreSQL 데이터 영속성**: 생성된 게임 결과, 채팅(행동) 로그 및 플레이어 통계를 비동기로 영구 저장
- 🌐 **소설(사건록) 자동 생성**: 플레이 종료 후 그동안의 행동 로그(채팅)를 시간순으로 종합하여 한 편의 소설이나 기록으로 제공

## 🛠 기술 스택 (Tech Stack)
### Backend
- **Framework**: FastAPI (Python 3.11)
- **Database (RDBMS)**: PostgreSQL 16 (SQLAlchemy, Alembic)
- **In-Memory Cache**: Redis 7
- **AI Engine (선택)**: vLLM 서버 통신 구조
- **Scheduler**: APScheduler (백그라운드 게임 상태 DB 동기화용)

### DevOps & Deployment
- **Containerization**: Docker & Docker Compose
- **CI/CD**: GitHub Actions (Main 브랜치 Push 시 AWS EC2 자동 배포)

---

## 🚀 시작하기 (Getting Started)

### 1️⃣ 로컬 환경 세팅 (Local Development)

#### 필수 조건 (Prerequisites)
- Docker Desktop
- Conda (또는 Python 가상환경)

#### 실행 방법 (How to Run)
1. 리포지토리 클론 및 폴더 이동
   ```bash
   git clone <repository-url>
   cd demo-repository
   ```
2. 패키지 설치
   ```bash
   pip install -r requirements.txt
   ```
3. 로컬 DB 및 캐시 서버(Docker) 띄우기
   ```bash
   docker-compose up -d
   ```
4. 초기화 스크립트 실행 (DB 마이그레이션 및 시나리오 메타데이터 로딩)
   ```bash
   python init_db.py
   alembic upgrade head
   python -m app.loader
   ```
5. 서버 실행!
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   > 💡 **Tip**: 이 모든 과정을 단축하려면 쉘 스크립트 실행 `sh start.sh`

---

## 🚢 배포 (Deployment)
해당 프로젝트는 단일 고성능 클라우드 인스턴스(AWS EC2) 환경에 맞춰 `Docker Compose`를 활용하여 배포되도록 최적화되어 있습니다.

자동 배포 파이프라인 (CI/CD) 세팅은 상세한 문서를 참고 부탁드립니다.
👉 [[배포 상세 가이드 읽기 (DEPLOYMENT.md)]](DEPLOYMENT.md)

### 프로덕션 서버 실행 명령어 (Manual)
만약 자동 배포를 사용하지 않는다면, 서버 환경에서 다음 명령어 1줄로 끝납니다.
```bash
docker-compose -f docker-compose.prod.yml up -d --build
```
> 주의: 서버에 미리 `.env` 파일과 도커 엔진이 설치되어 있어야 합니다.

---

## 📁 디렉토리 구조 (Directory Structure)
```text
📦 demo-repository
 ┣ 📂 app               # FastAPI 메인 애플리케이션 코드
 ┃ ┣ 📂 api             # 라우터 (엔드포인트 API: 게임, 시나리오 등)
 ┃ ┣ 📂 crud            # DB 접근을 위한 모델 조작 로직 (ChatLog 등)
 ┃ ┣ 📂 db_models       # SQLAlchemy 기반 Table 스키마 정의
 ┃ ┣ 📂 schemas         # Pydantic 타입 검증 모델 (Request/Response)
 ┃ ┣ 📂 services        # 핵심 비즈니스(게임) 로직 및 NPC 처리 담당
 ┃ ┣ 📂 workers         # 스케줄러 (Redis 데이터 백업 등)
 ┃ ┣ 📜 main.py         # 애플리케이션 진입점 (Entry Point)
 ┃ ┗ 📜 redis_client.py # Redis 통신 및 상태 저장/로딩 모듈
 ┣ 📂 scenarios         # 게임 내러티브, 노드(방), 아이템 및 NPC 상세 데이터
 ┣ 📜 docker-compose.prod.yml # AWS 배포용 설정파일 (전체 서비스)
 ┣ 📜 docker-compose.yml      # 로컬 개발용 DB/Redis 
 ┣ 📜 Dockerfile              # 백엔드 서버 빌드용
 ┣ 📜 requirements.txt        # 파이썬 의존성 패키지 (Numpy, Apscheduler 포함)
 ┣ 📜 DEPLOYMENT.md           # 클라우드/운영 배포 설계 안내서
 ┗ 📜 ARCHITECTURE.md         # 서버 구조 및 데이터 패스 아키텍처 다이어그램
```

## 📝 설계 철학 (Architecture Vision)
게임 로직 특성상 순간적인 트래픽(동시 다발적인 액션 턴 진행 요청)이 발생할 수 있습니다.
최대한 병목을 줄이기 위해, "디스크(DB) 접근은 최소화" 하고, **"게임 진행은 모두 메모리(Redis)에서 해결"**한 뒤 안정화 되었을 때 DB로 Bulk 저장하도록 설계되었습니다 (`app/workers/sync_worker.py` 참조).
