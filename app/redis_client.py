import time
import json # Keeping just in case for edge fallbacks
import redis
from typing import Optional, Dict, Any
from app.config import REDIS_URL

class RedisClient:
    def __init__(self):
        self.client = redis.from_url(REDIS_URL, decode_responses=True)
        self.ttl = 3600  # 1 hour expiration for safety

    def get_game_state(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        RedisJSON을 사용해 게임 상태 전체 딕셔너리를 한 번에 가져옵니다.
        """
        key = f"game:{game_id}:data"
        # json().get() returns the exact python dictionary structure we saved
        data = self.client.json().get(key)
        if not data:
            return None
            
        return data

    def set_game_state(self, game: Any):
        """
        RedisJSON을 사용해 문자열로 직렬화(json.dumps)하지 않고 곧바로 트리를 통째로 저장합니다.
        game: sqlalchemy Games model instance
        """
        game_id = str(game.id)
        key = f"game:{game_id}:data"
        
        # npc_data 구조 변환 (DB의 list -> Redis의 dict)
        npc_stats_dict = {}
        if game.npc_data and isinstance(game.npc_data, dict) and "npcs" in game.npc_data:
            for npc in game.npc_data["npcs"]:
                if "npc_id" in npc:
                    npc_stats_dict[npc["npc_id"]] = npc
        
        mapping = {
            "meta_data": game.world_meta_data,
            "npc_stats": npc_stats_dict,
            "player_info": game.player_data,
            "summary": game.summary,
            "status": game.status,
            "last_updated": time.time()
        }
        
        # '$' = JSON root path
        self.client.json().set(key, "$", mapping)
        self.client.expire(key, self.ttl)

    def get_player_info(self, game_id: str) -> Optional[Dict[str, Any]]:
        key = f"game:{game_id}:data"
        # JSONPath syntax (.player_info) to retrieve just the nested dict without loading the rest
        data = self.client.json().get(key, "$.player_info")
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    def update_player_info(self, game_id: str, player_info: dict):
        key = f"game:{game_id}:data"
        if self.client.exists(key):
            self.client.json().set(key, "$.player_info", player_info)
            self.client.expire(key, self.ttl)

    def delete_game_state(self, game_id: str):
        key = f"game:{game_id}:data"
        self.client.delete(key)
    
    def get_all_active_games(self) -> list[str]:
        keys = self.client.keys("game:*:data")
        return [k.split(":")[1] for k in keys]

    # --- Global Scenario Cache Methods ---
    def set_scenario_assets(self, scenario_title: str, assets_dict: dict):
        """서버 구동 시 무거운 시나리오 에셋 YAML 정보 전체를 JSON 트리로 메모리에 영구 등재합니다."""
        key = f"scenario:{scenario_title}:assets"
        self.client.json().set(key, "$", assets_dict)
        # Not setting ttl. Scenarios live forever in cache.

    def get_scenario_assets(self, scenario_title: str) -> Optional[Dict[str, Any]]:
        """캐시된 시나리오 데이터를 통 단위 dict로 즉시 반환"""
        key = f"scenario:{scenario_title}:assets"
        return self.client.json().get(key)

# 싱글톤 인스턴스
_redis_instance = None

def get_redis_client() -> RedisClient:
    global _redis_instance
    if _redis_instance is None:
        _redis_instance = RedisClient()
    return _redis_instance
