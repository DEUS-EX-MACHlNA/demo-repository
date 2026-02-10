import sys
import os
from app.database import SessionLocal
from app.db_models.game import Games 
from app.services.game import GameService
from app.crud import game as crud_game

# ensure we can import app
sys.path.append(os.getcwd())

def test_process_turn():
    db = SessionLocal()
    try:
        # Get the first game
        game = db.query(Games).first()
        if not game:
            print("No game found. Please ensure a game exists.")
            return

        print(f"Testing process_turn with Game ID: {game.id}")
        
        user_input = {"chat_input": "Hello world", "npc_name": "unknown"}
        
        # Test process_turn (mock execution)
        print("\nTesting process_turn...")
        # Note: process_turn signature: cls.process_turn(db, game_id, input_data, game)
        # We need to pass arguments correctly
        result = GameService.process_turn(db, game.id, user_input, game)
        
        if result:
            print("process_turn Result Keys:", result.keys())

        # Verify DB Updates
        db.refresh(game)
        print(f"Post-Process Turn: {game.world_meta_data.get('state', {}).get('turn')}")
        
        # Check if turn incremented (assuming it started at 1 and delta adds 1)
        # Note: DayController mock/real execution seems to return turn_increment=1 based on previous logs
        
        # Verify ChatLog
        from app.db_models.chat_log import ChatLogs
        last_log = db.query(ChatLogs).filter_by(game_id=game.id).order_by(ChatLogs.id.desc()).first()
        if last_log:
            print(f"ChatLog Found! ID: {last_log.id}, Turn: {last_log.turn_number}")
        print("Test Passed!")
        
    except Exception as e:
        print(f"Test Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_process_turn()
