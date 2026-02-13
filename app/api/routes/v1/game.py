
# 여기는 특정 시나리오로 실행하게 되면 DB에 접근해서 게임을 실행시켜 달라는 api를 호출하는 곳입니다.
from datetime import datetime

from app.services.game import GameService
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.db_models.game import Games
from app.schemas.status import GameStatus
from app.db_models.scenario import Scenario
from app.schemas.client_sync import GameClientSyncSchema
from app.crud import game as crud_game
from app.schemas.request_response import StepRequestSchema, StepResponseSchema, NightResponseResult
from app.schemas.night import (
    NightLogResponse,
    NightExposedLog,
    FullLogRef,
    NightEffects,
    PlayerEffect,
    NpcDelta,
    UiData,
)


router = APIRouter(tags=["game"])


@router.get("/", summary="게임 목록 조회", response_model=list[dict])
def get_games(db: Session = Depends(get_db)):
    games = crud_game.get_all_games(db)
    # 필요한 필드만 추출 (id, summary)
    return [
        {
            "game_id": g.id,
            "summary": g.summary if g.summary else {}
        }
        for g in games
    ]
# 대화 요청(낮)
@router.post("/{game_id}/step", summary="게임 대화 요청", response_model=StepResponseSchema)
def step_game(game_id: int, request: StepRequestSchema, db: Session = Depends(get_db)) -> StepResponseSchema:
    # 1. 게임 정보 조회
    game = db.query(Games).filter(Games.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")

    result = GameService.process_turn(db, game_id, request, game)

    return result

# 게임 id를 받아서 진행된 게임을 불러오기
@router.get("/start/{game_id}", summary="진행중인 게임 시작", response_model=GameClientSyncSchema)
def get_game(game_id: int, db: Session = Depends(get_db)) -> GameClientSyncSchema:
    try:
        game = GameService.start_game(db, game_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")

    return game

# 밤 파이프라인 실행
@router.post("/{game_id}/night_dialogue", summary="밤 파이프라인 실행", response_model=NightResponseResult)
def night_game(game_id: int, db: Session = Depends(get_db)) -> NightResponseResult:
    game = db.query(Games).filter(Games.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")

    result = GameService.process_night(db, game_id, game)
    return result


# 밤의 대화 결과 조회(재접속/히스토리)
@router.get("/{game_id}/show_night_dialogue", summary="밤의 대화 요청", response_model=NightLogResponse)
def get_night_log(game_id: int, db: Session = Depends(get_db)):

    mock_response = NightLogResponse(
        gameId=game_id,
        day=1, # TODO: 실제 게임 날짜 조회
        exposedLog=NightExposedLog(
            title="밤의 대화 기록 일부이긴 한데 일단은 mock데이터를 가지고 보냈고 추후 비즈니스 로직을 추가시킬 예정",
            lines=[
                "[새엄마] 오늘은 예절이 부족했어. 내일은 더 깊이 잠들게 해야겠어.",
                "[새아빠] 지하실 근처를 서성거렸지. 주의가 필요해.",
                "[동생] 누나... 나랑 놀자... 근데... 저기... 가지 마..."
            ]
        ),
        fullLogRef=FullLogRef(
            available=True,
            redacted=True
        ),
        effects=NightEffects(
            player=PlayerEffect(
                humanityDelta=-2,
                turnPenaltyNextDay=1,
                statusTagsAdded=["SUSPICION_RISING"]
            ),
            npcDeltas=[
                NpcDelta(id="stepmother", affectionDelta=-5, humanityDelta=0),
                NpcDelta(id="stepfather", affectionDelta=-2, humanityDelta=1),
                NpcDelta(id="brother", affectionDelta=3, humanityDelta=2)
            ]
        ),
        ui=UiData(
            resultText="밤의 대화 기록 일부\n- 새엄마: 오늘은 예절이 부족했어...\n- 새아빠: 지하실 근처를...\n- 동생: 누나... 나랑..."
        ),
        serverTime=datetime.utcnow()
    )
    return mock_response
