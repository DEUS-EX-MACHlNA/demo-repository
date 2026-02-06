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
from pydantic import BaseModel

from app.loader import ScenarioAssets, get_loader, load_scenario_assets
from app.models import (
    NightResult,
    ToolResult,
    WorldState,
)
from app.narrative import get_narrative_layer
from app.state import get_world_state_manager
from app.day_controller import get_day_controller
from app.night_controller import get_night_controller
from app.lock_manager import get_lock_manager
from app.ending_checker import check_ending, EndingCheckResult

# ============================================================
# 로깅 설정
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================
# Pydantic Models (Request/Response)
# ============================================================
class DayRequestBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/day 요청 바디"""
    user_id: str
    text: str


class DayResponseBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/day 응답"""
    dialogue: str
    ending: Optional[dict[str, Any]] = None  # 엔딩 도달 시
    debug: dict[str, Any] = {}


class NightRequestBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/night 요청 바디"""
    user_id: str


class NightResponseBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/night 응답"""
    dialogue: str
    night_conversation: list[dict[str, str]]  # NPC 그룹 대화
    ending: Optional[dict[str, Any]] = None  # 엔딩 도달 시
    debug: dict[str, Any] = {}


class ScenarioInfoResponse(BaseModel):
    """시나리오 정보 응답"""
    scenario_id: str
    title: str
    genre: str
    turn_limit: int
    npcs: list[str]
    items: list[str]


class StateResponse(BaseModel):
    """상태 조회 응답"""
    user_id: str
    scenario_id: str
    state: dict[str, Any]


# ============================================================
# 애플리케이션 설정
# ============================================================
SCENARIOS_BASE_PATH = Path(__file__).parent.parent / "scenarios"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    logger.info(f"Starting scenario server...")
    logger.info(f"Scenarios path: {SCENARIOS_BASE_PATH}")

    loader = get_loader(SCENARIOS_BASE_PATH)
    available = loader.list_scenarios()
    logger.info(f"Available scenarios: {available}")

    yield

    logger.info("Shutting down scenario server...")


app = FastAPI(
    title="Interactive Scenario Game Server",
    description="텍스트 기반 인터랙티브 시나리오 게임 서버 (낮/밤 분리 파이프라인)",
    version="0.2.0",
    lifespan=lifespan,
)


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
    2) WorldState 조회
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

        def apply_and_persist() -> WorldState:
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
                narrative.render_day,
                tool_result.event_description,
                tool_result.state_delta,
                world_after,
                assets
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
    2) WorldState 조회
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

        def apply_and_persist() -> WorldState:
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
                narrative.render_night,
                world_after,
                assets,
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
# API 엔드포인트
# ============================================================
@app.post(
    "/v1/scenario/{scenario_id}/day",
    response_model=DayResponseBody,
    summary="낮 턴 실행",
    description="유저 입력을 받아 낮 턴을 진행합니다. (LockManager → DayController → EndingChecker)"
)
async def day_turn(
    scenario_id: str,
    body: DayRequestBody
) -> DayResponseBody:
    """낮 턴 실행"""
    logger.info(f"Day request: scenario={scenario_id}, user={body.user_id}")

    loader = get_loader(SCENARIOS_BASE_PATH)
    if not loader.exists(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")

    try:
        dialogue, ending, debug = await execute_day_pipeline(
            body.user_id,
            scenario_id,
            body.text
        )

        return DayResponseBody(
            dialogue=dialogue,
            ending=ending,
            debug=debug
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing day turn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post(
    "/v1/scenario/{scenario_id}/night",
    response_model=NightResponseBody,
    summary="밤 페이즈 실행",
    description="밤 페이즈를 진행합니다. (NightController → EndingChecker)"
)
async def night_phase(
    scenario_id: str,
    body: NightRequestBody
) -> NightResponseBody:
    """밤 페이즈 실행"""
    logger.info(f"Night request: scenario={scenario_id}, user={body.user_id}")

    loader = get_loader(SCENARIOS_BASE_PATH)
    if not loader.exists(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")

    try:
        dialogue, conversation, ending, debug = await execute_night_pipeline(
            body.user_id,
            scenario_id,
        )

        return NightResponseBody(
            dialogue=dialogue,
            night_conversation=conversation,
            ending=ending,
            debug=debug
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing night phase: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get(
    "/v1/scenario/{scenario_id}",
    response_model=ScenarioInfoResponse,
    summary="시나리오 정보 조회"
)
async def get_scenario_info(scenario_id: str) -> ScenarioInfoResponse:
    """시나리오 기본 정보 조회"""
    loader = get_loader(SCENARIOS_BASE_PATH)
    if not loader.exists(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")

    assets = load_scenario_assets(scenario_id)

    return ScenarioInfoResponse(
        scenario_id=scenario_id,
        title=assets.scenario.get("title", ""),
        genre=assets.scenario.get("genre", ""),
        turn_limit=assets.get_turn_limit(),
        npcs=assets.get_all_npc_ids(),
        items=assets.get_all_item_ids(),
    )


@app.get(
    "/v1/scenario/{scenario_id}/state/{user_id}",
    response_model=StateResponse,
    summary="유저 상태 조회"
)
async def get_user_state(scenario_id: str, user_id: str) -> StateResponse:
    """특정 유저의 시나리오 상태 조회"""
    loader = get_loader(SCENARIOS_BASE_PATH)
    if not loader.exists(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")

    assets = load_scenario_assets(scenario_id)
    wsm = get_world_state_manager()
    state = wsm.get_state(user_id, scenario_id, assets)

    return StateResponse(
        user_id=user_id,
        scenario_id=scenario_id,
        state=state.to_dict()
    )


@app.delete(
    "/v1/scenario/{scenario_id}/state/{user_id}",
    summary="유저 상태 리셋"
)
async def reset_user_state(scenario_id: str, user_id: str) -> dict:
    """특정 유저의 시나리오 상태 리셋"""
    wsm = get_world_state_manager()
    wsm.reset_state(user_id, scenario_id)
    # LockManager도 리셋
    lock_manager = get_lock_manager()
    lock_manager.reset()
    return {"status": "ok", "message": f"State reset for user={user_id}, scenario={scenario_id}"}


@app.get("/v1/scenarios", summary="사용 가능한 시나리오 목록")
async def list_scenarios() -> dict:
    """사용 가능한 모든 시나리오 목록 반환"""
    loader = get_loader(SCENARIOS_BASE_PATH)
    scenarios = loader.list_scenarios()
    return {"scenarios": scenarios}


@app.get("/health", summary="헬스 체크")
async def health_check() -> dict:
    """서버 상태 확인"""
    return {"status": "healthy"}


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
