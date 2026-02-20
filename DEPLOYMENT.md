# Maratang 게임 서버 배포 계획

이 문서는 Maratang 게임 서버를 프로덕션 환경에 배포하기 위한 전략을 설명합니다. FastAPI 서버, PostgreSQL 데이터베이스, Redis 캐시, 그리고 특화된 LLM 서버를 포함하므로 신중한 배포 계획이 필요합니다.

## 1. 아키텍처: 올인원 GPU 서버 (선택됨)

**올인원(All-in-One)** 전략을 선택하셨습니다. 고성능 GPU 서버(예: RTX 6000 / g7e.2xlarge) 하나를 사용하여 모든 서비스를 구동하는 방식으로, 관리의 단순함과 성능 면에서 훌륭한 선택입니다.

### 하드웨어 평가
- **GPU (RTX 6000)**: 일반적으로 24GB 또는 48GB VRAM을 탑재하고 있습니다.
    - **워크로드**: `Kanana-8B` 모델(FP16/BF16)은 약 **16GB VRAM**을 필요로 합니다.
    - **적합성**: RTX 6000은 모델 구동과 동시 접속자 처리를 위한 캐시(KV Cache) 공간까지 충분히 확보 가능합니다.
- **예산 (약 40만원)**: 클라우드 GPU 서비스(RunPod/Lambda 등 시간당 $0.5~$0.8)를 이용하거나 저렴한 호스팅의 월 단위 계약을 하기에 충분한 예산입니다.

### 소프트웨어 스택 (Docker Compose)
모든 컴포넌트를 **Docker Compose**를 사용하여 단일 서버 내에 배포합니다. 각 컨테이너는 외부와 격리된 내부 네트워크를 통해 통신합니다.

| 서비스 | 컨테이너 이름 | 역할 | 자원 할당 |
| :--- | :--- | :--- | :--- |
| **Nginx** | `nginx` | **리버스 프록시**: HTTPS 처리 및 트래픽 분배 (Frontend/Backend). | CPU/RAM 소량 |
| **FastAPI** | `app` | **게임 서버**: 게임 로직 수행, DB/Redis/LLM과 통신. | CPU 보통 |
| **PostgreSQL** | `db` | **데이터베이스**: 사용자 정보 및 게임 기록 영구 저장. | RAM/IO 보통 |
| **Redis** | `redis` | **캐시**: 빠른 응답을 위한 게임 상태 임시 저장. | RAM 소량 |
| **vLLM** | `vllm` | **AI 엔진**: API를 통해 `Kanana-8B` 모델 서빙. | **GPU 전체 사용** |

### 아키텍처 다이어그램

```mermaid
graph TB
    user((사용자))
    
    subgraph "싱글 GPU 서버 (Docker Host)"
        subgraph "내부 네트워크 (maratang-net)"
            nginx[Nginx<br/>Port 80/443]
            app[FastAPI App<br/>Port 8000]
            db[(PostgreSQL<br/>Port 5432)]
            redis[(Redis<br/>Port 6379)]
            vllm[vLLM AI Engine<br/>Port 8000]
        end
        
        gpu[RTX 6000 GPU]
    end

    user -->|HTTPS| nginx
    nginx -->|리버스 프록시| app
    app -->|Read/Write| redis
    app -->|데이터 저장| db
    app -->|텍스트 생성 요청| vllm
    vllm -.->|CUDA 연산| gpu
```

### 데이터 흐름
1.  **사용자**가 `https://your-game.com`에 접속합니다.
2.  **Nginx**가 요청을 받아 내부의 `app:8000`으로 전달합니다.
3.  **App**은 먼저 **Redis**에서 게임 상태를 확인합니다.
4.  AI 생성이 필요하면, **App**은 `http://vllm:8000/v1/chat/completions`로 요청을 보냅니다.
5.  **vLLM**은 **GPU**를 사용해 텍스트를 생성하고 **App**에 반환합니다.
6.  **App**은 결과를 **Redis**에 업데이트하고 필요 시 **DB**에 백그라운드로 동기화합니다.
7.  **App**이 사용자에게 최종 응답을 보냅니다.

### 저장소 전략 (Storage)
- **데이터베이스**: Docker Volume(`pg_data`)을 서버의 고속 SSD/NVMe에 매핑하여 데이터를 영구 보존합니다.
- **모델 가중치**: Docker Volume(`huggingface_cache`)을 사용하여 컨테이너 재시작 시마다 16GB 모델을 다시 다운로드하지 않도록 합니다.

---

## 2. 배포 단계 (Docker Compose 전략)

로컬 개발 환경과 유사하게 **Docker Compose**를 사용하지만, 프로덕션 설정을 적용합니다.

### 1단계: 준비 (로컬)
1.  **Docker 최적화**:
    - `Dockerfile`을 멀티 스테이지 빌드로 작성하여 이미지 크기를 최소화합니다.
    - `.dockerignore`를 설정하여 불필요한 파일 제외.
2.  **환경 설정**:
    - `.env.prod` 파일을 생성하여 운영 환경의 비밀번호와 설정을 관리합니다.
    - **주의**: `.env` 파일은 절대 Git에 올리지 않습니다.
3.  **VLLM 설정**:
    - `docker-compose.yml` 리소스 예약 설정에 GPU 접근 권한(`driver: nvidia`)을 명시합니다.

### 2단계: 서버 세팅 (원격)
1.  **서버 확보**: GPU 클라우드(Lambda Labs, RunPod 등)에서 인스턴스 생성.
2.  **기본 설치**: Ubuntu 22.04 LTS + NVIDIA Driver 설치 확인.
3.  **Docker 설치**:
    - Docker Engine & Docker Compose 설치.
    - **NVIDIA Container Toolkit** 설치 (Docker가 GPU를 쓰기 위해 필수).

### 3단계: 배포 실행
1.  **코드 전송**: Git Clone 또는 SCP로 프로젝트를 서버에 복사합니다.
2.  **설정**: 서버에 `.env` 파일을 생성합니다.
3.  **실행**:
    ```bash
    docker-compose -f docker-compose.prod.yml up -d --build
    ```
4.  **DB 마이그레이션**:
    ```bash
    docker-compose -f docker-compose.prod.yml exec app alembic upgrade head
    ```

### 4단계: 운영 관리
1.  **SSL 인증서 (HTTPS)**:
    - Certbot을 사용해 무료 SSL 인증서를 발급받고 Nginx에 적용합니다.
2.  **모니터링**:
    - `docker logs`로 로그 확인.
    - `htop`, `nvtop`으로 CPU/GPU 자원 모니터링.
3.  **백업**:
    - 주기적으로 `pg_dump`를 실행하여 DB를 백업하는 스크립트 작성.

---

## 3. 프론트엔드 전략 (Unity)

Unity 클라이언트 배포는 **방식 A (WebGL)**를 추천합니다.

### 방식 A: WebGL (추천)
Unity WebGL 빌드 파일을 서버의 **Nginx**를 통해 직접 서비스합니다.

1.  **빌드**: Unity 프로젝트를 WebGL로 빌드합니다.
2.  **배포**: 생성된 빌드 폴더(`Build/`, `index.html`)를 서버의 Nginx 경로(예: `/var/www/html`)에 업로드합니다.
3.  **Nginx 라우팅**:
    - 루트 경로 `/` 요청 시 Unity의 `index.html`을 보여줍니다.
    - `/api` 경로는 백엔드(`app:8000`)로 프록시합니다.
4.  **장점**:
    - **CORS 문제 없음**: 프론트와 백엔드가 같은 도메인을 사용하므로 보안 설정이 매우 간단해집니다.
    - **성능**: Nginx가 정적 파일을 매우 빠르게 처리합니다.
    - **접근성**: 사용자가 설치 없이 브라우저로 바로 접속 가능합니다.

### 방식 B: PC/모바일 앱 (Standalone)
`.exe`나 `.apk` 파일을 배포하는 방식입니다.

1.  **설정**: 클라이언트가 로컬호스트가 아닌 실제 도메인(`https://your-game.com`)을 바라보도록 설정해야 합니다.

---

## 4. 즉시 실행 항목 (배포 전)

본격적인 배포 전에 다음 작업들을 수행해야 합니다:

1.  **[Task] Docker Compose 분리**: 개발용(`dev`)과 배포용(`prod`) 설정 파일 분리.
2.  **[Task] Nginx 설정**: 리버스 프록시 및 정적 파일 호스팅을 위한 Nginx 설정 작성.
3.  **[Task] 비밀값 관리**: 하드코딩된 비밀번호들을 환경 변수(.env)로 이동.
4.  **[Task] LLM 안정성**: vLLM 서비스 실패 시 자동 재시작 설정 추가.
