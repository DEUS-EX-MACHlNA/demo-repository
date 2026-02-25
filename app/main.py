"""
app/main.py
FastAPI 메인 애플리케이션

텍스트 기반 인터랙티브 시나리오 게임 서버
- /day: 낮 파이프라인 (LockManager → DayController → EndingChecker)
- /night: 밤 파이프라인 (NightController → EndingChecker)
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException

from app.loader import ScenarioAssets, get_loader, load_scenario_assets
from app.schemas import (
    NightResult,
    ToolResult,
    WorldStatePipeline,
    NightRequestBody,
    NightResponseResult,
    ScenarioInfoResponse,
    StateResponse,
    EndingCheckResult,
)
from app.narrative import get_narrative_layer
from app.state import get_world_state_manager
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
from app.lock_manager import get_lock_manager
from app.ending_checker import check_ending


from app.api.routes.v1 import game as v1_game_router
from app.api.routes.v1 import scenario as v1_scenario_router

from app.config import SCENARIOS_BASE_PATH


# ============================================================
# 로깅 설정
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================
# 애플리케이션 설정
# ============================================================
# 시나리오 기본 경로 (환경변수나 설정 파일로 변경 가능)



from app.workers.sync_worker import start_scheduler, shutdown_scheduler, sync_game_state_to_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    logger.info(f"Starting scenario server...")
    logger.info(f"Scenarios path: {SCENARIOS_BASE_PATH}")
    
    # Background Scheduler Start
    start_scheduler()
    logger.info("Background sync scheduler started.")

    loader = get_loader(SCENARIOS_BASE_PATH)
    available = loader.list_scenarios()
    logger.info(f"Available scenarios: {available}")

    yield

    logger.info("Shutting down scenario server...")
    
    # Final Sync & Shutdown
    logger.info("Performing final DB sync...")
    await sync_game_state_to_db()
    
    shutdown_scheduler()
    logger.info("Background sync scheduler shutdown.")


app = FastAPI(
    title="Interactive Scenario Game Server",
    description="텍스트 기반 인터랙티브 시나리오 게임 서버 (낮/밤 분리 파이프라인)",
    version="0.2.0",
    lifespan=lifespan,
)

# API 라우터 포함
app.include_router(v1_game_router.router, prefix="/api/v1/game", tags=["game"])
app.include_router(v1_scenario_router.router, prefix="/api/v1/scenario", tags=["scenario"])


# ============================================================
# 개발 서버 실행
# ============================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
