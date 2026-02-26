import os
import sys
import time
from unittest.mock import patch
from contextlib import contextmanager

from app.database import SessionLocal
from app.services.game import GameService
from app.crud import game as crud_game
from app.schemas.request_response import StepRequestSchema
from app.schemas.tool import ToolResult
from app.schemas.game_state import StateDelta
from app.redis_client import get_redis_client

@contextmanager
def suppress_output():
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

def patched_day_controller_process(*args, **kwargs):
    return ToolResult(
        intent="대화",
        event_description=["테스트 이벤트입니다. (Mock)"],
        state_delta=StateDelta().to_dict(),
        npc_response="안녕? 오늘 하루 어때?"
    )

def patched_narrative_layer_render(*args, **kwargs):
    return "테스트 응답 나레이션 시뮬레이션입니다."

def patched_check_ending(*args, **kwargs):
    from app.schemas.ending import EndingCheckResult
    return EndingCheckResult(reached=False)

def benchmark_redis_performance():
    print("="*60)
    print("Redis Fetch vs DB Fetch Performance Benchmark (Mocked LLM)")
    print("="*60)

    db = SessionLocal()
    game_id = 59  # 요구사항: game_id는 59번으로
    iterations = 50
    warmup_iterations = 5

    try:
        game = crud_game.get_game_by_id(db, game_id)
        if not game:
            print(f"Game {game_id} not found!")
            return

        # 요구사항: input data는 한글로 적당한걸 넣게 만들어줘
        input_data = StepRequestSchema(
            user_id=game.user_id,
            chat_input="저기요, 오늘 날씨가 참 좋네요! 다들 어떻게 지내시나요?",
            timestamp="2024-01-01T00:00:00"
        )
        
        redis_client = get_redis_client()

        print(f"Benchmarking {iterations} iterations for each mode (Warmup: {warmup_iterations})...\n")

        with patch("app.services.game.get_day_controller") as mock_dc, \
             patch("app.services.game.get_narrative_layer") as mock_nl, \
             patch("app.services.game.check_ending", side_effect=patched_check_ending):
            
            mock_dc.return_value.process.side_effect = patched_day_controller_process
            mock_nl.return_value.render.side_effect = patched_narrative_layer_render
            
            # Warmup
            print("Warming up...")
            for _ in range(warmup_iterations):
                 GameService.process_turn(db, game_id, input_data, game)
            print(" Done.\n")

            # Mode A: Redis Fetch Mode
            print("Running Redis Fetch Mode...")
            start_time = time.time()
            for i in range(iterations):
                GameService.process_turn(db, game_id, input_data, game=None)
                if i % 10 == 0:
                    print(f"Redis mode iteration {i}")
            end_time = time.time()
            print(" Done.")
            
            avg_redis = (end_time - start_time) / iterations
            print(f"[Redis Fetch Mode] Average Time: {avg_redis:.4f} sec/turn")

            # Mode B: DB Fetch Mode
            print("Running DB Fetch Mode...")
            start_time_db = time.time()
            for i in range(iterations):
                db.refresh(game)
                GameService.process_turn_db_only(db, game_id, input_data, game)
                if i % 10 == 0:
                    print(f"DB mode iteration {i}")
            end_time_db = time.time()
            print(" Done.")

            avg_db = (end_time_db - start_time_db) / iterations
            print(f"[DB Fetch Mode]    Average Time: {avg_db:.4f} sec/turn")

            # Comparison
            diff = avg_db - avg_redis
            improvement = (diff / avg_db) * 100 if avg_db > 0 else 0
            
            print("\n" + "-"*60)
            print(f"Time Saved per Turn (Redis vs DB): {diff:.4f} sec")
            print(f"Performance Improvement: {improvement:.2f}%")
            print("-"*60)
            
            if diff > 0:
                print("Redis fetch optimization is faster!")
            else:
                print("No significant difference (check network/local DB latency) or DB is faster.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    benchmark_redis_performance()
