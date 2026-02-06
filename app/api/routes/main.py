# Routes 메인
# 여기서 fastapi 앱을 생성하고 라우터를 포함합니다.
# 근데 맨 앞 main에 되어 있네여
from fastapi import FastAPI, APIRouter
from app.routes.v1 import scenario, game

# FastAPI 앱 생성

app = FastAPI()
# 라우터 포함
api_router = APIRouter()

api_router.include_router(scenario.router, prefix="/v1/scenario", tags=["scenario"])
api_router.include_router(game.router, prefix="/v1/game", tags=["game"])