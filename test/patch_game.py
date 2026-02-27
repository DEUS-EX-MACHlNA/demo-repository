import sys

def patch():
    with open("app/services/game.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    process_turn_def = "    @classmethod\n    def process_turn("
    parts = content.split(process_turn_def)
    if len(parts) != 2:
        print("Could not find process_turn correctly")
        sys.exit(1)
        
    process_turn_code = parts[1]
    process_night_def = "    @staticmethod\n    def _create_night_response_data"
    subparts = process_turn_code.split(process_night_def)
    
    process_turn_body = subparts[0]
    after_turn = process_night_def + subparts[1]
    
    new_func = process_turn_def + process_turn_body
    new_func = new_func.replace("def process_turn(", "def process_turn_db_only(")
    
    old_step1 = """        # ── Step 1: world state 생성 (Redis 우선) ──
        cached_state = None
        load_source = "DB"
        try:
            cached_state = redis_client.get_game_state(str(game_id))
        except Exception as e:
            logger.warning(f"Failed to get game state from Redis: {e}")

        if cached_state:
            load_source = "Redis"
            logger.debug(f"Loaded game state from Redis for game_id={game_id}")
            # Redis 데이터를 기반으로 WorldStatePipeline 생성
            meta = cached_state.get("meta_data", {})
            npc_stats = cached_state.get("npc_stats", {})
            player_info = cached_state.get("player_info", {})
            
            # DB 모델에 Redis 데이터 반영
            game.world_meta_data = meta
            game.npc_data = {"npcs": list(npc_stats.values())}
            game.player_data = player_info

            # 공통 함수를 사용하여 WorldState 생성
            world_state = cls._create_world_state(game)
            
        else:
            logger.debug(f"Cache miss for game_id={game_id}, loading from DB")
            world_state = cls._create_world_state(game)"""
            
    new_step1 = """        # ── Step 1: world state 생성 (DB 단독) ──
        load_source = "DB_ONLY"
        logger.debug(f"Loading game state from DB exclusively for game_id={game_id}")
        world_state = cls._create_world_state(game)"""
    
    if old_step1 in new_func:
        new_func = new_func.replace(old_step1, new_step1)
    else:
        print("Failed to replace step 1")
        sys.exit(1)
        
    old_step8_redis = """        # # Redis 캐시 업데이트
        try:
            npc_stats = {}
            if game.npc_data and "npcs" in game.npc_data:
                for npc in game.npc_data["npcs"]:
                    if "npc_id" in npc:
                        npc_stats[npc["npc_id"]] = npc
            
            redis_client.set_game_state(
                str(game_id),
                game.world_meta_data,
                npc_stats,
                game.player_data
            )
            logger.debug(f"Updated Redis cache for game_id={game_id}")
        except Exception as e:
            logger.error(f"Failed to update Redis cache: {e}")"""
            
    new_step8_redis = """        # Redis 캐시 업데이트 생략 (DB 전용 모드)"""
    
    if old_step8_redis in new_func:
        new_func = new_func.replace(old_step8_redis, new_step8_redis)
    else:
        print("Failed to replace step 8 redis")
        sys.exit(1)
        
    final_content = parts[0] + process_turn_def + process_turn_body + new_func + after_turn
    with open("app/services/game.py", "w", encoding="utf-8") as f:
        f.write(final_content)
    print("patch successful!")

if __name__ == "__main__":
    patch()
