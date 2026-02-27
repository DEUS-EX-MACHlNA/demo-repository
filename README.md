# 🎪 Maratang Game Server (마라탕 게임 서버)

Maratang은 생존 추리 스릴러 방탈출 게임을 위한 텍스트/LLM 기반 인터랙티브 백엔드 게임 서버입니다. 
AI(LLM) 기반의 시나리오 진행, NPC 상호작용, 인벤토리 관리 및 조사(추리) 시스템을 제공합니다.

## ✨ 주요 특징 (Features)
- 🤖 **LLM NPC & Agent 시스템**: `vLLM` (Kanana-8B 모델) 및 전용 에이전트를 기반으로 사용자의 입력에 반응하는 지능형 NPC와 스토리 나레이터 구현
- 🌍 **낮/밤 파이프라인 및 상태 머신**: 턴제 기반 게임 진행, 플레이어 이동, 낮/밤 페이즈 분리(`DayController`, `NightController`), 기믹 해독 및 락키(`LockManager`) 처리
- 🎒 **아이템 & 상태 시스템**: 복잡한 아이템 획득 및 사용 로직(`ItemAcquirer`, `ItemUseResolver`), 각종 상태 이상 부여(`StatusEffectManager`)
- ⚡ **Redis 기반 고속 상태 관리**: 동시 접속자 처리 및 빠른 턴 진행을 위한 인메모리 게임 데이터 캐싱 (`O(1)` 속도로 게임 상태 읽기/쓰기 지원)
- 📊 **PostgreSQL 데이터 영속성**: 생성된 게임 결과, 채팅(행동) 로그 및 플레이어 통계를 백그라운드 워커를 통해 비동기로 영구 저장
- 🌐 **소설(사건록) 자동 생성 (Postprocess)**: 플레이 종료 후 그동안의 행동 로그(채팅)를 시간순으로 종합하여 한 편의 소설이나 기록으로 제공

## 🛠 기술 스택 (Tech Stack)
### Backend
- **Framework**: FastAPI (Python 3.11)
- **Database (RDBMS)**: PostgreSQL 16 (SQLAlchemy, Alembic)
- **In-Memory Cache**: Redis 7
- **AI Engine**: vLLM 서버 통신, 커스텀 LLM 에이전트 아키텍처
- **Scheduler**: APScheduler (백그라운드 게임 상태 DB 동기화용)

### DevOps & Deployment
- **Containerization**: Docker & Docker Compose

---

## 🚀 시작하기 (Getting Started)

### 1️⃣ 로컬 환경 세팅 (Local Development)

#### 필수 조건 (Prerequisites)
- Docker Desktop
- Conda (또는 Python 가상환경) - 본 프로젝트는 기본적으로 `deus` 환경을 사용하도록 세팅되어 있습니다.

#### 실행 방법 (How to Run)
1. 리포지토리 클론 및 폴더 이동
   ```bash
   git clone <repository-url>
   cd demo-repository
   ```
2. Conda 환경 활성화 및 패키지 설치
   ```bash
   conda activate deus
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
   > 💡 **Tip**: 이 모든 과정을 단축하려면 쉘 스크립트 실행 `sh start.sh` (`deus` conda 환경 경로가 `/opt/anaconda3` 기준으로 맞춰져 있습니다)

---

## 🚢 배포 (Deployment)
해당 프로젝트는 단일 고성능 클라우드 인스턴스(AWS EC2) 환경에 맞춰 `Docker Compose`를 활용하여 배포되도록 최적화되어 있습니다.

배포와 관련된 상세한 클라우드 아키텍처/명세 문서는 `docs/` 폴더 내 자료를 참고 부탁드립니다.

### 프로덕션 서버 실행 명령어 (Manual)
만약 자동 배포를 사용하지 않는다면, 서버 환경에서 다음 명령어 1줄로 끝납니다.
```bash
docker-compose -f docker-compose.prod.yml up -d --build
```
> 주의: 서버에 미리 `.env` 파일과 도커 엔진이 설치되어 있어야 합니다.

---

## 📁 디렉토리 구조 (Directory Structure)
```text
📦 main-project
 ┣ 📂 app               # FastAPI 메인 애플리케이션 코드
 ┃ ┣ 📂 agents          # LLM 처리 전담 자율 에이전트
 ┃ ┣ 📂 api             # 라우터 (엔드포인트 API: 낮/밤, 시나리오 등)
 ┃ ┣ 📂 crud            # DB 접근을 위한 모델 조작 로직 (ChatLog 등)
 ┃ ┣ 📂 db_models       # SQLAlchemy 기반 Table 스키마 정의
 ┃ ┣ 📂 llm             # 기반 LLM 모델과의 통신 인터페이스 모듈
 ┃ ┣ 📂 postprocess     # 게임 종료 후 소설 생성 등 후처리 파이프라인
 ┃ ┣ 📂 schemas         # Pydantic 타입 검증 모델 (Request/Response)
 ┃ ┣ 📂 services        # 핵심 비즈니스 로직
 ┃ ┣ 📂 workers         # 스케줄러 (Redis 데이터 백업 등)
 ┃ ┣ 📜 day_controller.py / night_controller.py # 낮, 밤 파이프라인
 ┃ ┣ 📜 rule_engine.py  # 상태 머신 제어를 위한 룰셋 엔진
 ┃ ┣ 📜 main.py         # 애플리케이션 진입점 (Entry Point)
 ┃ ┗ 📜 redis_client.py # Redis 통신 및 상태 저장/로딩 모듈
 ┣ 📂 docs              # 시스템 아키텍처 다이어그램 및 설계/명세 문서
 ┣ 📂 scenarios         # 게임 내러티브, 노드(방), 아이템 및 NPC 상세 데이터
 ┣ 📜 docker-compose.prod.yml # AWS 배포용 설정파일 (전체 서비스)
 ┣ 📜 docker-compose.yml      # 로컬 개발용 DB/Redis 
 ┣ 📜 Dockerfile              # 백엔드 서버 빌드용
 ┣ 📜 requirements.txt        # 파이썬 의존성 패키지
 ┗ 📜 start.sh / start_prod.sh # 시작 유틸리티 스크립트
```

## 📝 설계 철학 (Architecture Vision)

### 1. 백엔드 시스템 (Backend Engine)
- **메모리 중심의 고속 처리**: 게임 로직 특성상 순간적인 트래픽(동시 다발적인 액션 턴 진행 요청)이 발생할 수 있습니다. 최대한 병목을 줄이기 위해, "디스크(DB) 접근은 최소화" 하고, **"게임 진행은 모두 메모리(Redis)에서 해결"**하도록 최우선 설계되었습니다.
- **비동기 영속화**: 상태가 안정화되었을 때 백그라운드 워커(`app/workers/sync_worker.py`)를 통해 DB로 Bulk 저장하여 데이터 안정성과 사용자 체감 응답 속도를 동시에 확보합니다.
- **견고한 상태 관리**: 백엔드 파이프라인(낮/밤 컨트롤러)과 `LockManager` 등의 룰 엔진을 겹겹이 배치하여, 사용자나 AI의 예측 불가능한 입력으로부터 게임의 논리적 무결성을 보호합니다.

### 2. AI 언어 모델 (Model & LLM)
- **컴퓨팅 자원의 분리 (Decoupling)**: 무거운 연산이 필요한 딥러닝 추론(GPU) 노드(vLLM)를 메인 웹 API 서버와 물리적/논리적으로 분리시켜, 서로 독립적인 장애 격리 및 스케일링이 가능하도록 구성했습니다.
- **제어 가능한 자율 에이전트 (Controllable Agents)**: 생성형 AI 특유의 환각(Hallucination) 현상이 실제 게임 진행(아이템, 추리 단서 등)을 망가뜨리지 못하도록, 프롬프트 엔지니어링과 백엔드 상태 검증 로직이 결합된 전담 에이전트 구조(`app/agents/`)를 채택했습니다.
- **LoRA를 활용한 전문성 향상**: 역할과 화자(스토리 나레이터, 개별 NPC 등)의 문풍 차이를 극대화하기 위해, 거대 모델에만 의존하지 않고 각 상황에 맞춰 특수 파인튜닝된 LoRA 엔드포인트를 라우팅 적용하여 몰입감을 높입니다.
