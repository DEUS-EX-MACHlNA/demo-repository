import json
import redis
from typing import Optional, Dict, Any
from app.config import REDIS_URL

class RedisClient:
    def __init__(self):
        self.client = redis.from_url(REDIS_URL, decode_responses=True)
        self.ttl = 3600  # 1 hour expiration for safety

    def get_game_state(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Redis에서 게임 상태를 가져옵니다.
        state, npc, player 키를 가진 딕셔너리를 반환합니다.
        """
        key = f"game:{game_id}:data"
        data = self.client.hgetall(key)
        if not data:
            return None
            
        # JSON 문자열을 파싱하여 반환
        return {
            "meta_data": json.loads(data.get("meta_data", "{}")),
            "npc_stats": json.loads(data.get("npc_stats", "{}")),
            "player_info": json.loads(data.get("player_info", "{}")),
            "last_updated": data.get("last_updated")
        }

    def set_game_state(self, game_id: str, meta_data: dict, npc_stats: dict, player_info: dict):
        """
        Redis에 게임 상태를 저장합니다.
        각 필드는 JSON으로 직렬화되어 저장됩니다.
        """
        key = f"game:{game_id}:data"
        mapping = {
            "meta_data": json.dumps(meta_data, ensure_ascii=False),
            "npc_stats": json.dumps(npc_stats, ensure_ascii=False),
            "player_info": json.dumps(player_info, ensure_ascii=False),
            "last_updated": "now" # TODO: timestamp
        }
        self.client.hset(key, mapping=mapping)
        self.client.expire(key, self.ttl)

    def get_player_info(self, game_id: str) -> Optional[Dict[str, Any]]:
        """Redis에서 player_info만 가져옵니다."""
        key = f"game:{game_id}:data"
        data = self.client.hget(key, "player_info")
        if not data:
            return None
        return json.loads(data)

    def update_player_info(self, game_id: str, player_info: dict):
        """Redis에서 player_info만 업데이트합니다."""
        key = f"game:{game_id}:data"
        # 키 존재 여부 확인 후 업데이트
        if self.client.exists(key):
            self.client.hset(key, "player_info", json.dumps(player_info, ensure_ascii=False))
            self.client.expire(key, self.ttl)

    def delete_game_state(self, game_id: str):
        """게임 상태를 Redis에서 삭제합니다."""
        key = f"game:{game_id}:data"
        self.client.delete(key)
    
    def get_all_active_games(self) -> list[str]:
        """활성 게임 ID 목록을 반환합니다 (스캔 방식)"""
        # 주의: 운영 환경에서는 scan_iter 권장
        keys = self.client.keys("game:*:data")
        return [k.split(":")[1] for k in keys]

# 싱글톤 인스턴스
_redis_instance = None

def get_redis_client() -> RedisClient:
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = RedisClient()
    return _redis_instance
