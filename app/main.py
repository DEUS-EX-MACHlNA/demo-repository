"""
app/main.py
FastAPI 메인 애플리케이션

텍스트 기반 인터랙티브 시나리오 게임 서버
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

from app.controller import get_controller
from app.loader import ScenarioAssets, get_loader, load_scenario_assets
from app.models import (
    NightResult,
    StepResponse,
    ToolCall,
    ToolResult,
    WorldState,
    merge_deltas,
)
from app.narrative import get_narrative_layer
from app.parser import get_parser
from app.state import get_world_state_manager
from app.tools import execute_tool, get_night_controller

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
class StepRequestBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 요청 바디"""
    user_id: str
    text: str


class StepResponseBody(BaseModel):
    """POST /v1/scenario/{scenario_id}/step 응답"""
    dialogue: str
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
# 시나리오 기본 경로 (환경변수나 설정 파일로 변경 가능)
SCENARIOS_BASE_PATH = Path(__file__).parent.parent / "scenarios"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    # Startup
    logger.info(f"Starting scenario server...")
    logger.info(f"Scenarios path: {SCENARIOS_BASE_PATH}")

    # 로더 초기화
    loader = get_loader(SCENARIOS_BASE_PATH)
    available = loader.list_scenarios()
    logger.info(f"Available scenarios: {available}")

    yield

    # Shutdown
    logger.info("Shutting down scenario server...")


app = FastAPI(
    title="Interactive Scenario Game Server",
    description="텍스트 기반 인터랙티브 시나리오 게임 서버",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================
# 핵심 파이프라인 실행
# ============================================================
async def execute_pipeline(
    user_id: str,
    scenario_id: str,
    user_text: str
) -> tuple[str, bool, dict[str, Any]]:
    """
    메인 파이프라인 실행

    파이프라인:
    1) loader로 assets 로드
    2) world_before = wsm.get_state(...)
    3) parsed = parser.parse(user_text, assets, world_before)
    4) toolcall = controller.decide(parsed, world_before, assets)
    5) (state_delta, text_fragment) = chosen_tool(...)
    6) night = night_controller.run(world_before, assets)
    7) 병렬 실행:
       - world_after = wsm.apply_delta(..., merge(state_delta, night_delta)) + persist
       - dialogue = narrative.render(...)
    8) response 반환

    Returns:
        tuple[dialogue, debug]
    """
    start_time = time.time()
    debug: dict[str, Any] = {
        "user_id": user_id,
        "scenario_id": scenario_id,
        "input_text": user_text[:100],  # 로그용으로 잘라서 저장
        "steps": [],
    }

    try:
        # ============================================================
        # Step 1: Assets 로드
        # ============================================================
        step_start = time.time()
        assets = load_scenario_assets(scenario_id)
        debug["steps"].append({
            "step": "load_assets",
            "duration_ms": (time.time() - step_start) * 1000,
            "scenario_title": assets.scenario.get("title", "unknown"),
        })

        # ============================================================
        # Step 2: 현재 상태 조회
        # ============================================================
        step_start = time.time()
        wsm = get_world_state_manager()
        world_before = wsm.get_state(user_id, scenario_id, assets)
        debug["steps"].append({
            "step": "get_state",
            "duration_ms": (time.time() - step_start) * 1000,
            "turn": world_before.turn,
        })

        # ============================================================
        # Step 3: 입력 파싱
        # ============================================================
        step_start = time.time()
        parser = get_parser()
        parsed = parser.parse(user_text, "", "", assets, world_before)
        debug["steps"].append({
            "step": "parse",
            "duration_ms": (time.time() - step_start) * 1000,
            "intent": parsed.intent,
            "target": parsed.target,
        })

        # ============================================================
        # Step 4: Tool 선택
        # ============================================================
        step_start = time.time()
        controller = get_controller()
        toolcall = controller.decide(parsed, world_before, assets)
        debug["steps"].append({
            "step": "decide_tool",
            "duration_ms": (time.time() - step_start) * 1000,
            "tool_name": toolcall.tool_name,
            "tool_args": toolcall.args,
        })

        # ============================================================
        # Step 5: 선택된 Tool 실행 (tool_1/2/3 중 하나)
        # ============================================================
        step_start = time.time()
        tool_result: ToolResult = execute_tool(
            toolcall.tool_name,
            toolcall.args,
            world_before,
            assets
        )
        debug["steps"].append({
            "step": "execute_tool",
            "duration_ms": (time.time() - step_start) * 1000,
            "tool_name": toolcall.tool_name,
            "state_delta_keys": list(tool_result.state_delta.keys()),
        })

        # ============================================================
        # Step 6: Night Comes 실행 (항상 1회)
        # ============================================================
        step_start = time.time()
        night_controller = get_night_controller()
        night_result: NightResult = night_controller.run(world_before, assets)
        debug["steps"].append({
            "step": "night_comes",
            "duration_ms": (time.time() - step_start) * 1000,
            "dialogue_rounds": len(night_result.night_conversation),
        })

        # ============================================================
        # Step 7: 병렬 실행 - Delta 적용 & Narrative 렌더링
        # ============================================================
        # 델타 병합
        merged_delta = merge_deltas(tool_result.state_delta, night_result.night_delta)
        debug["merged_delta"] = merged_delta

        step_start = time.time()

        # 병렬 실행 설계:
        # - apply_delta와 persist는 순차적 (apply 후 persist)
        # - narrative.render는 world_after가 필요하므로, apply_delta 완료 후 실행
        # 실제로는 apply_delta 먼저 완료 후 render 호출하는 구조로 구현

        async def apply_and_persist() -> WorldState:
            """델타 적용 및 영속화"""
            world_after = wsm.apply_delta(user_id, scenario_id, merged_delta, assets)
            wsm.persist(user_id, scenario_id, world_after)
            return world_after

        # apply_delta 먼저 실행
        world_after = await asyncio.to_thread(apply_and_persist)

        # render는 world_after 필요
        narrative = get_narrative_layer()
        dialogue = await asyncio.to_thread(
            narrative.render,
            tool_result.text_fragment,
            night_result.night_description,
            world_before,
            world_after,
            assets
        )

        debug["steps"].append({
            "step": "apply_and_render",
            "duration_ms": (time.time() - step_start) * 1000,
            "turn_after": world_after.turn,
            "dialogue_length": len(dialogue),
        })

        # ============================================================
        # Step 8: 결과 반환
        # ============================================================
        debug["total_duration_ms"] = (time.time() - start_time) * 1000
        debug["success"] = True

        return dialogue, debug

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        debug["error"] = str(e)
        debug["success"] = False
        raise


# ============================================================
# API 엔드포인트
# ============================================================
@app.post(
    "/v1/scenario/{scenario_id}/step",
    response_model=StepResponseBody,
    summary="시나리오 한 스텝 진행",
    description="유저 입력을 받아 시나리오를 한 턴 진행하고 결과를 반환합니다."
)
async def step_scenario(
    scenario_id: str,
    body: StepRequestBody
) -> StepResponseBody:
    """
    시나리오 한 스텝 진행

    Args:
        scenario_id: 시나리오 ID
        body: {user_id, text}

    Returns:
        {dialogue, debug}
    """
    logger.info(f"Step request: scenario={scenario_id}, user={body.user_id}")

    # 시나리오 존재 확인
    loader = get_loader(SCENARIOS_BASE_PATH)
    if not loader.exists(scenario_id):
        raise HTTPException(
            status_code=404,
            detail=f"Scenario not found: {scenario_id}"
        )

    try:
        dialogue, debug = await execute_pipeline(
            body.user_id,
            scenario_id,
            body.text
        )

        return StepResponseBody(
            dialogue=dialogue,
            debug=debug
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing step: {e}", exc_info=True)
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
