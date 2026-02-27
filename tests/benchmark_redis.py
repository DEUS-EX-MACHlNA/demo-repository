import os
import sys
import time
from contextlib import contextmanager
from app.database import SessionLocal
from app.services.game import GameService
from app.crud import game as crud_game
from app.schemas.request_response import StepRequestSchema

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

def benchmark_redis_performance():
    print("="*60)
    print("Redis vs DB Performance Benchmark")
    print("="*60)

    db = SessionLocal()
    game_id = 7 # Use a valid game ID
    iterations = 50
    warmup_iterations = 5

    try:
        game = crud_game.get_game_by_id(db, game_id)
        if not game:
            print("Game not found!")
            return

        input_data = StepRequestSchema(
            user_id=game.user_id,
            chat_input="Benchmark Input",
            timestamp="2024-01-01T00:00:00"
        )

        print(f"Benchmarking {iterations} iterations for each mode (Warmup: {warmup_iterations})...\n")

        # Warmup
        print("Warming up...", end="")
        with suppress_output():
            for _ in range(warmup_iterations):
                 GameService.process_turn(db, game_id, input_data, game)
        print(" Done.\n")

        # Mode A: Redis Only (Current Optimized State)
        print("Running Redis Mode...", end="")
        start_time = time.time()
        with suppress_output():
            for i in range(iterations):
                GameService.process_turn(db, game_id, input_data, game)
        end_time = time.time()
        print(" Done.")
        
        avg_redis = (end_time - start_time) / iterations
        print(f"[Redis Mode] Average Time: {avg_redis:.4f} sec/turn")

        # Mode B: Redis + DB (Simulating Old State)
        print("Running DB Mode...", end="")
        start_time_db = time.time()
        with suppress_output():
            for i in range(iterations):
                GameService.process_turn(db, game_id, input_data, game)
                crud_game.update_game(db, game) # Simulate synchronous DB write
        end_time_db = time.time()
        print(" Done.")

        avg_db = (end_time_db - start_time_db) / iterations
        print(f"[DB Mode]    Average Time: {avg_db:.4f} sec/turn")

        # Comparison
        diff = avg_db - avg_redis
        improvement = (diff / avg_db) * 100 if avg_db > 0 else 0
        
        print("\n" + "-"*60)
        print(f"Time Saved per Turn: {diff:.4f} sec")
        print(f"Performance Improvement: {improvement:.2f}%")
        print("-"*60)
        
        if diff > 0:
            print("Redis optimization is faster!")
        else:
            print("No significant difference (check network/local DB latency).")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    benchmark_redis_performance()
