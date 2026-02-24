from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.redis_client import get_redis_client
from app.crud import game as crud_game
from app.db_models.game import Games
import json
import logging

logger = logging.getLogger(__name__)

# Silence scheduler logs
logging.getLogger('apscheduler').setLevel(logging.WARNING)

async def sync_game_state_to_db():
    """
    Redis의 게임 상태를 DB에 동기화합니다.
    주기적으로 실행되거나, 셧다운 시 호출될 수 있습니다.
    """
    redis_client = get_redis_client()
    
    # 1. 활성 게임 목록 가져오기
    # 실무에서는 scan_iter 등을 사용하여 키를 찾습니다.
    # 여기서는 간단히 구현 (redis_client에 get_all_active_games 추가 필요)
    try:
        active_game_ids = redis_client.get_all_active_games()
    except Exception as e:
        logger.error(f"[SyncWorker] Failed to get active games from Redis: {e}")
        return

    if not active_game_ids:
        return

    # logger.info(f"[SyncWorker] Syncing {len(active_game_ids)} games to DB...")
    
    db = SessionLocal()
    try:
        for game_id_str in active_game_ids:
            try:
                game_id = int(game_id_str)
                cached = redis_client.get_game_state(game_id_str)
                
                if not cached:
                    continue
                
                # DB에서 게임 로드
                game = crud_game.get_game_by_id(db, game_id)
                if not game:
                    continue
                
                # 데이터 업데이트
                # 주의: DB의 최신성을 덮어씌우지 않도록 낙관적 락이나 버전 관리가 필요할 수 있음
                # 여기서는 Redis가 Truth라고 가정
                
                if cached.get("meta_data"):
                    game.world_meta_data = cached["meta_data"]
                
                if cached.get("player_info"):
                    game.player_data = cached["player_info"]
                
                if cached.get("npc_stats"):
                    # Redis에는 dict {id: data} 형태로 저장됨
                    # DB에는 list [data, data] 형태로 저장됨
                    # 이를 변환해줘야 함
                    npc_dict = cached["npc_stats"]
                    game.npc_data = {"npcs": list(npc_dict.values())}
                
                # 변경사항 마킹 (JSON 필드 감지용)
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(game, "world_meta_data")
                flag_modified(game, "player_data")
                flag_modified(game, "npc_data")
                
                db.add(game)
                
                # 30분 이상 유휴(Idle) 상태인지 확인 후 메모리 비우기 (Force Quit 대응)
                import time
                IDLE_TIMEOUT_SECONDS = 600  # 10분
                last_updated = cached.get("last_updated", 0)
                
                if isinstance(last_updated, (int, float)) and (time.time() - last_updated) > IDLE_TIMEOUT_SECONDS:
                    # 이번 루프에서 커밋할 대상 추가
                    logger.info(f"알림: 게임 {game_id}가 장시간(10분) 이용되지 않아 DB 저장 후 종료되었습니다.")
                    # 삭제 대기 목록에 추가하거나 바로 삭제할 수 있지만, DB 커밋 안정성을 위해
                    # 커밋 성공 여부와 상관없이 삭제하는 것은 위험할 수 있으므로
                    # 이 블록에서는 db가 커밋될 것을 가정하고 삭제합니다.
                    redis_client.delete_game_state(game_id_str)
                
            except Exception as e:
                logger.error(f"[SyncWorker] Failed to sync game {game_id_str}: {e}")
        
        db.commit()
        # logger.info(f"[SyncWorker] Synced {len(active_game_ids)} games to DB.")
        
    except Exception as e:
        logger.error(f"[SyncWorker] Critical error during sync: {e}")
        db.rollback()
    finally:
        db.close()

scheduler = AsyncIOScheduler()
scheduler.add_job(
    sync_game_state_to_db, 
    'interval', 
    seconds=60, 
    misfire_grace_time=60,  # 1분(60초)까지 늦게 실행되는 것을 허용
    coalesce=True,          # 지연된 실행이 여러 번 쌓이면 한 번만 실행
    max_instances=1         # 동시에 중복 실행 방지
)

def start_scheduler():
    scheduler.start()

def shutdown_scheduler():
    scheduler.shutdown()
