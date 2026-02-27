import sys

def patch():
    with open("app/services/game.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Find process_turn definition
    process_turn_def = "    @classmethod\n    def process_turn("
    parts = content.split(process_turn_def)
    if len(parts) != 2:
        print("Could not find process_turn correctly")
        sys.exit(1)

    process_turn_code = parts[1]
    process_night_def = "    @classmethod\n    def process_turn_db_only("
    subparts = process_turn_code.split(process_night_def)

    if len(subparts) != 2:
        print("Could not find process_turn_db_only correctly")
        sys.exit(1)

    process_turn_body = subparts[0]
    after_turn = process_night_def + subparts[1]

    # Replace the existing process_turn with the new logic
    new_process_turn = """    @classmethod
    def process_turn(
        cls,
        db: Session,
        game_id: int,
        input_data: StepRequestSchema,
        game: Games = None, # Optional: only provided if fallback to DB occurs in router
    ) -> StepResponseSchema:
        \"\"\"
        낮 파이프라인 실행:
        오직 Redis에서만 상태를 로드합니다! 
        Redis에 상태가 없을 경우 DB에서 게임을 조회하고 Redis를 갱신한 뒤 처리합니다.
        \"\"\"
        debug: Dict[str, Any] = {"game_id": game_id, "steps": []}
        redis_client = get_redis_client()

        # ── Step 1: world state 생성 (Redis Only) ──
        cached_state = None
        load_source = "Redis"
        try:
            cached_state = redis_client.get_game_state(str(game_id))
        except Exception as e:
            logger.warning(f"Failed to get game state from Redis: {e}")

        if not cached_state:
            logger.warning(f"Redis cache MISS for game_id={game_id}! Falling back to DB load.")
            load_source = "DB_Fallback"
            if game is None:
                # 라우터에서 game을 넘기지 않은 경우 직접 조회해야 함
                game = crud_game.get_game_by_id(db, game_id)
                if not game:
                    raise ValueError(f"Game {game_id} not found in DB!")
                    
            world_state = cls._create_world_state(game)
        else:
            logger.debug(f"Loaded game state from Redis for game_id={game_id}")
            # Redis에 데이터가 있으면 DB 게임 모델을 가상으로 생성 (저장을 위해)
            if game is None:
                # DB 조회를 유예하거나 빈 껍데기를 쓸 수도 있지만, 
                # 나레이션이나 이력 저장을 위해 최소한의 DB 인스턴스가 필요할 수 있음.
                # 그러나 성능의 극대화를 위해 game 속성만 덮어씌움.
                game = Games(id=game_id)
                
            meta = cached_state.get("meta_data", {})
            npc_stats = cached_state.get("npc_stats", {})
            player_info = cached_state.get("player_info", {})
            
            game.world_meta_data = meta
            game.npc_data = {"npcs": list(npc_stats.values())}
            game.player_data = player_info

            world_state = cls._create_world_state(game)

        # ── Step 2: Scenario Assets 로드 ──
        # assets 로드 시 DB의 Scenario 객체가 필요할 수 있음
        # 만약 Redis 전용 모드에서 DB 접근이 막힌다면 문제가 됨
        # 그러나 _scenario_to_assets 안에는 file fallback(loader) 로직이 있음
        assets = _scenario_to_assets(game)

        # ── Step 3: LockManager - 정보 해금 ──
        lock_manager = get_lock_manager()
        locks_data = assets.extras.get("locks", {})
        lock_result = lock_manager.check_unlocks(world_state, locks_data)

        # ── Step 3.5: StatusEffectManager - 만료 효과 해제 ──
        from app.status_effect_manager import get_status_effect_manager
        sem = get_status_effect_manager()
        sem.tick(world_state.turn, world_state)

        # ── Step 4: DayController - 낮 턴 실행 ──
        user_input = input_data.to_combined_string()
        day_controller = get_day_controller()
        tool_result: ToolResult = day_controller.process(
            user_input,
            world_state,
            assets,
        )
        debug["steps"].append({
            "step": "day_turn",
            "state_delta": tool_result.state_delta,
        })
        
        logger.debug(f"DayController result: {tool_result}")

        # ── Step 5: Delta 적용 ──
        world_after = _apply_delta(world_state, tool_result.state_delta, assets)

        # ── Step 5.5: ItemAcquirer - 자동 아이템 획득 스캔 ──
        from app.item_acquirer import get_item_acquirer
        acquirer = get_item_acquirer()
        acq_result = acquirer.scan(world_after, assets)
        if acq_result.newly_acquired:
            world_after = _apply_delta(world_after, acq_result.acquisition_delta, assets)
            for acq_item_id in acq_result.newly_acquired:
                acq_item_def = assets.get_item_by_id(acq_item_id)
                acq_item_name = acq_item_def.get("name", acq_item_id) if acq_item_def else acq_item_id
                tool_result.event_description.append(f"'{acq_item_name}'을(를) 발견했다!")

        # ── Step 5.6: day_action_log 축적 (밤 가족회의 안건용) ──
        day_log_entry = {
            "turn": world_after.turn,
            "input": user_input,
            "intent": tool_result.intent,
            "events": tool_result.event_description,
        }
        world_after.day_action_log.append(day_log_entry)

        # ── Step 6: EndingChecker - 엔딩 체크 ──
        ending_result = check_ending(world_after, assets)
        ending_info = None
        if ending_result.reached:
            ending_info = {
                "ending_id": ending_result.ending.ending_id,
                "name": ending_result.ending.name,
                "epilogue_prompt": ending_result.ending.epilogue_prompt,
            }
            game.status = GameStatus.ENDING.value
            if ending_result.triggered_delta:
                game.status = GameStatus.ENDING.value
                _apply_delta(world_after, ending_result.triggered_delta.to_dict(), assets)

        # ── Step 7: NarrativeLayer - 나레이션 생성 ──
        try:
            narrative_layer = get_narrative_layer()
            if ending_info:
                narrative = narrative_layer.render_ending(
                    ending_info,
                    world_after,
                    assets,
                )
            else:
                narrative = narrative_layer.render(
                    world_state=world_after,
                    assets=assets,
                    event_description=tool_result.event_description,
                    state_delta=tool_result.state_delta,
                    npc_response=tool_result.npc_response
                )
        except Exception as e:
             logger.error(f"[GameService] NarrativeLayer failed: {e}")
             narrative = ""
        
        # ── Step 7.5: Update Game Summary ──
        current_summary = game.summary
        if current_summary:
            game.summary = f"{current_summary}\\n{narrative}"
        else:
            game.summary = narrative
        if game.id is not None and getattr(game, "_sa_instance_state", None) is not None:
             flag_modified(game, "summary")

        # ── Step 8: Update Game State & Cache ──
        # 로컬 객체 업데이트
        cls._world_state_to_games(game, world_after, assets)
        
        # Redis 캐시 갱신 (항상)
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
            logger.error(f"Failed to update Redis cache: {e}")

        # 6. 저장 (DB) - Redis 온리(Only) 정책에 따라 매턴 동기식 DB 저장을 제거하거나 분리.
        #    사용자 요구사항에 따라: Redis에서만 데이터 Fetch -> 로직 처리 -> Redis 재저장.
        #    DB 저장은 제외 (또는 비동기 처리)
        
        # 다만 현재 로그 테이블은 분리되어 있어서 로그만 따로 쌓음 (DB 병목 요소 중 하나지만 로그 유지를 위해 남김)
        if load_source == "DB_Fallback":
            # 폴백이었으면 DB에 최신 상태 한번 저장해줌
            if game.id is not None and getattr(game, "_sa_instance_state", None) is not None:
                db.commit()

        user_content = input_data.chat_input
        current_turn = world_after.turn

        log_db = SessionLocal()
        try:
            create_chat_log(
                log_db, game_id, LogType.DIALOGUE, "Player", user_content, current_turn
            )
            
            # System Narrative Logging
            create_chat_log(
                log_db, game_id, LogType.NARRATIVE, "System", narrative, world_after.turn
            )
            
            # Save summary along with the logs using this separate session
            log_game = log_db.query(Games).filter(Games.id == game_id).first()
            if log_game:
                log_game.summary = game.summary
                flag_modified(log_game, "summary")
                log_db.commit()
        finally:
            log_db.close()

        if game.status == GameStatus.ENDING.value:
            if game.id is not None and getattr(game, "_sa_instance_state", None) is not None:
                 db.commit()
            redis_client.delete_game_state(str(game_id))
            logger.info(f"Game {game_id} ended at turn {world_after.turn}. Synced to DB and removed from Redis.")
        else:
            logger.info(f"Turn {world_after.turn} processed (Source: {load_source}, Redis: Updated)")

        # ── Assemble state_result for frontend ──
        _delta = tool_result.state_delta

        sr_npc_stats = _delta.get("npc_stats") or None
        sr_flags = _delta.get("flags") or None
        sr_inventory_add = _delta.get("inventory_add") or None
        sr_inventory_remove = _delta.get("inventory_remove") or None

        sr_npc_disabled_states = None
        active_effects = world_after.vars.get("status_effects", [])
        if active_effects:
            disabled = {}
            for eff in active_effects:
                if isinstance(eff, dict):
                    npc_id = eff.get("target_npc_id")
                    if npc_id:
                        disabled[npc_id] = {
                            "is_disabled": True,
                            "remaining_turns": max(0, eff.get("expires_at_turn", 0) - world_after.turn),
                            "reason": eff.get("applied_status", "unknown"),
                        }
            if disabled:
                sr_npc_disabled_states = disabled

        sr_vars = dict(_delta.get("vars", {}))
        sr_humanity = sr_vars.pop("humanity", None)
        sr_vars.pop("status_effects", None)

        current_node = None
        if isinstance(game.player_data, dict):
            current_node = game.player_data.get("current_node")

        state_result = {
            "npc_stats": sr_npc_stats,
            "flags": sr_flags,
            "inventory_add": sr_inventory_add,
            "inventory_remove": sr_inventory_remove,
            "item_state_changes": None,
            "npc_disabled_states": sr_npc_disabled_states,
            "humanity": sr_humanity,
            "current_node": current_node,
            "vars": sr_vars if sr_vars else {},
        }

        return StepResponseSchema(
            narrative=narrative,
            ending_info=ending_info,
            state_result=state_result,
            debug=debug,
        )
"""

    final_content = parts[0] + new_process_turn + "\n" + after_turn
    with open("app/services/game.py", "w", encoding="utf-8") as f:
        f.write(final_content)
    print("patch 2 successful!")

if __name__ == "__main__":
    patch()
