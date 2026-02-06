
# 여기는 특정 시나리오로 실행하게 되면 DB에 접근해서 게임을 실행시켜 달라는 api를 호출하는 곳입니다.
from app.services.game import GameService
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.db_models.game import Games, GameStatus
from app.db_models.scenario import Scenario  
from app.db_models.scenario import Scenario  
from app.schemas.client_sync import GameClientSyncSchema


router = APIRouter(tags=["game"])

# 게임 목록 조회, 아직 스키마는 만들지 말고 임시로 만들어준다

class StepRequestSchema(BaseModel):
    chat_input: str
    npc_name: str | None = None
    item_name: str | None = None

@router.get("/", summary="게임 목록 조회", response_model=list[dict])
def get_games(db: Session = Depends(get_db)):
    # TODO: 스키마를 구현하고 실제 게임 목록을 반환해야 합니다.
    return []

# 일단 LLM과 상호작용 하는 것을 먼저 구현

# 메모 조회
#@router.get("/{game_id}/memos", summary="게임 메모 조회", response_model=list[dict])


# 메모 생성
#@router.post("/{game_id}/memos", summary="게임 메모 생성", response_model=dict)

# 메모 수정
#@router.post("/{game_id}/memos/{memo_id}", summary="게임 메모 수정", response_model=dict)
# 메모 삭제
#@router.delete("/{game_id}/memos/{memo_id}", summary="게임 메모 삭제")

# 대화 요청

"""
대화로 할 수 있는거

받게 되는건 그냥 요청 객체 하나

변하게 되는건 아마 월드,플레이어,npc 다 바뀌겠지


1. npc와 대화
2. 그냥 엑션
3. 아이템 사용
"""
@router.post("/{game_id}/step", summary="게임 대화 요청")
def step_game(game_id: int, request: StepRequestSchema, db: Session = Depends(get_db)) -> dict:
    # 1. 게임 정보 조회
    game = db.query(Games).filter(Games.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")
    
    result = GameService.process_turn(db, game_id, request.dict(), game)
    
    return result

# 게임 id를 받아서 진행된 게임을 불러오기
@router.get("start/{game_id}", summary="진행중인 게임 시작", response_model=dict)
def get_game(game_id: int, db: Session = Depends(get_db)) -> GameClientSyncSchema:
    try:
        game = GameService.start_game(db, game_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다.")
    
    return game

# 밤에 대화 시작

