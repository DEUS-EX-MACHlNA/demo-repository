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
# 낮 파이프라인
# ============================================================
async def execute_day_pipeline(
    user_id: str,
    scenario_id: str,
    user_text: str
) -> tuple[str, Optional[dict], dict[str, Any]]:
    """
    낮 파이프라인 실행

    파이프라인:
    1) Assets 로드
    2) WorldStatePipeline 조회
    3) LockManager.check_unlocks() - 정보 해금
    4) DayController.process() - 낮 턴 실행 (turn += 1)
    5) Delta 적용 & 저장
    6) EndingChecker.check() - 엔딩 체크
    7) NarrativeLayer.render() - 나레이션 생성

    Returns:
        tuple[dialogue, ending_info, debug]
    """
    start_time = time.time()
    debug: dict[str, Any] = {
        "user_id": user_id,
        "scenario_id": scenario_id,
        "pipeline": "day",
        "input_text": user_text[:100],
        "steps": [],
    }

    try:
        # Step 1: Assets 로드
        step_start = time.time()
        assets = load_scenario_assets(scenario_id)
        debug["steps"].append({
            "step": "load_assets",
            "duration_ms": (time.time() - step_start) * 1000,
        })

        # Step 2: 현재 상태 조회
        step_start = time.time()
        wsm = get_world_state_manager()
        world_before = wsm.get_state(user_id, scenario_id, assets)
        debug["steps"].append({
            "step": "get_state",
            "duration_ms": (time.time() - step_start) * 1000,
            "turn": world_before.turn,
        })

        # Step 3: LockManager - 정보 해금
        step_start = time.time()
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_before, locks_data)
        debug["steps"].append({
            "step": "lock_check",
            "duration_ms": (time.time() - step_start) * 1000,
            "newly_unlocked": [info.info_id for info in lock_result.newly_unlocked],
        })

        # Step 4: DayController - 낮 턴 실행
        step_start = time.time()
        day_controller = get_day_controller()
        tool_result: ToolResult = day_controller.process(
            user_text,
            world_before,
            assets,
        )
        debug["steps"].append({
            "step": "day_turn",
            "duration_ms": (time.time() - step_start) * 1000,
            "state_delta": tool_result.state_delta,
        })

        # Step 5: Delta 적용 & 저장
        step_start = time.time()

        def apply_and_persist() -> WorldStatePipeline:
            world_after = wsm.apply_delta(user_id, scenario_id, tool_result.state_delta, assets)
            wsm.persist(user_id, scenario_id, world_after)
            return world_after

        world_after = await asyncio.to_thread(apply_and_persist)
        debug["steps"].append({
            "step": "apply_delta",
            "duration_ms": (time.time() - step_start) * 1000,
            "turn_after": world_after.turn,
        })

        # Step 6: EndingChecker - 엔딩 체크
        step_start = time.time()
        ending_result: EndingCheckResult = check_ending(world_after, assets)
        ending_info = None
        if ending_result.reached:
            ending_info = {
                "ending_id": ending_result.ending.ending_id,
                "name": ending_result.ending.name,
                "epilogue_prompt": ending_result.ending.epilogue_prompt,
            }
            # 엔딩 delta 적용 (flag_set 등)
            if ending_result.triggered_delta:
                wsm.apply_delta(user_id, scenario_id, ending_result.triggered_delta, assets)
                wsm.persist(user_id, scenario_id, world_after)

        debug["steps"].append({
            "step": "ending_check",
            "duration_ms": (time.time() - step_start) * 1000,
            "reached": ending_result.reached,
        })

        # Step 7: NarrativeLayer - 나레이션 생성
        step_start = time.time()
        narrative = get_narrative_layer()

        # 엔딩 도달 시 엔딩 나레이션 생성
        if ending_info:
            dialogue = await asyncio.to_thread(
                narrative.render_ending,
                ending_info,
                world_after,
                assets
            )
        else:
            dialogue = await asyncio.to_thread(
                narrative.render,
                world_after,
                assets,
                tool_result.event_description,
                tool_result.state_delta,
                tool_result.npc_response,
            )
        debug["steps"].append({
            "step": "render",
            "duration_ms": (time.time() - step_start) * 1000,
            "dialogue_length": len(dialogue),
        })

        debug["total_duration_ms"] = (time.time() - start_time) * 1000
        debug["success"] = True

        return dialogue, ending_info, debug

    except Exception as e:
        logger.error(f"Day pipeline error: {e}", exc_info=True)
        debug["error"] = str(e)
        debug["success"] = False
        raise


# ============================================================
# 밤 파이프라인
# ============================================================
async def execute_night_pipeline(
    user_id: str,
    scenario_id: str,
) -> tuple[str, list[dict], Optional[dict], dict[str, Any]]:
    """
    밤 파이프라인 실행

    파이프라인:
    1) Assets 로드
    2) WorldStatePipeline 조회
    3) NightController.process() - 밤 페이즈 (turn 증가 없음)
    4) Delta 적용 & 저장
    5) EndingChecker.check() - 엔딩 체크
    6) NarrativeLayer.render_night() - 나레이션 생성

    Returns:
        tuple[dialogue, night_conversation, ending_info, debug]
    """
    start_time = time.time()
    debug: dict[str, Any] = {
        "user_id": user_id,
        "scenario_id": scenario_id,
        "pipeline": "night",
        "steps": [],
    }

    try:
        # Step 1: Assets 로드
        step_start = time.time()
        assets = load_scenario_assets(scenario_id)
        debug["steps"].append({
            "step": "load_assets",
            "duration_ms": (time.time() - step_start) * 1000,
        })

        # Step 2: 현재 상태 조회
        step_start = time.time()
        wsm = get_world_state_manager()
        world_before = wsm.get_state(user_id, scenario_id, assets)
        debug["steps"].append({
            "step": "get_state",
            "duration_ms": (time.time() - step_start) * 1000,
            "turn": world_before.turn,
        })

        # Step 3: NightController - 밤 페이즈
        step_start = time.time()
        night_controller = get_night_controller()
        night_result: NightResult = night_controller.process(world_before, assets)
        debug["steps"].append({
            "step": "night_phase",
            "duration_ms": (time.time() - step_start) * 1000,
            "conversation_rounds": len(night_result.night_conversation),
        })

        # Step 4: Delta 적용 & 저장
        step_start = time.time()

        def apply_and_persist() -> WorldStatePipeline:
            world_after = wsm.apply_delta(user_id, scenario_id, night_result.night_delta, assets)
            wsm.persist(user_id, scenario_id, world_after)
            return world_after

        world_after = await asyncio.to_thread(apply_and_persist)
        debug["steps"].append({
            "step": "apply_delta",
            "duration_ms": (time.time() - step_start) * 1000,
        })

        # Step 5: EndingChecker - 엔딩 체크
        step_start = time.time()
        ending_result: EndingCheckResult = check_ending(world_after, assets)
        ending_info = None
        if ending_result.reached:
            ending_info = {
                "ending_id": ending_result.ending.ending_id,
                "name": ending_result.ending.name,
                "epilogue_prompt": ending_result.ending.epilogue_prompt,
            }
            if ending_result.triggered_delta:
                wsm.apply_delta(user_id, scenario_id, ending_result.triggered_delta, assets)
                wsm.persist(user_id, scenario_id, world_after)

        debug["steps"].append({
            "step": "ending_check",
            "duration_ms": (time.time() - step_start) * 1000,
            "reached": ending_result.reached,
        })

        # Step 6: NarrativeLayer - 나레이션 생성
        step_start = time.time()
        narrative = get_narrative_layer()

        # 엔딩 도달 시 엔딩 나레이션 생성
        if ending_info:
            dialogue = await asyncio.to_thread(
                narrative.render_ending,
                ending_info,
                world_after,
                assets
            )
        else:
            dialogue = await asyncio.to_thread(
                narrative.render,
                world_after,
                assets,
                None,  # event_description
                None,  # state_delta
                None,  # npc_response
                night_result.night_conversation,
            )
        debug["steps"].append({
            "step": "render",
            "duration_ms": (time.time() - step_start) * 1000,
            "dialogue_length": len(dialogue),
        })

        debug["total_duration_ms"] = (time.time() - start_time) * 1000
        debug["success"] = True

        return dialogue, night_result.night_conversation, ending_info, debug

    except Exception as e:
        logger.error(f"Night pipeline error: {e}", exc_info=True)
        debug["error"] = str(e)
        debug["success"] = False
        raise

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
