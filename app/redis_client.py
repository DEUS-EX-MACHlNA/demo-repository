import redis
from app.config import REDIS_URL

def get_redis_client():
    """Redis 클라이언트를 반환합니다."""
    # decode_responses=True를 사용하여 바이트가 아닌 문자열로 반환받습니다.
    return redis.from_url(REDIS_URL, decode_responses=True)
