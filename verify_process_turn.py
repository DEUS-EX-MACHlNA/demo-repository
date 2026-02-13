import sys
import os
from app.database import SessionLocal
from app.db_models.game import Games 
from app.services.game import GameService
from app.crud import game as crud_game

# 이제부턴 여기는 휴지통이다


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


def make_mock_tool_result(user_input: str) -> ToolResult:
    # 1. 황동 열쇠 획득 (Acquire Key)
    if "황동 열쇠" in user_input:
        return ToolResult(
            event_description=[
                "당신은 조심스럽게 식탁으로 다가가 황동 열쇠를 집어들었습니다.",
                "차가운 금속의 감촉이 손끝에 전해집니다. 이제 이 열쇠로 무언가를 열 수 있을 것 같습니다."
            ],
            state_delta={
                "inventory_add": ["brass_key"],
                "vars": {},
                "npc_stats": {}
            }
        )
    
    # 2. 주인공 방으로 이동 (Move to Room)
    elif "내 방" in user_input:
        return ToolResult(
            event_description=[
                "당신은 주방을 빠져나와 복도를 지나, 익숙한 자신의 방으로 돌아왔습니다.",
                "문을 닫자 잠시나마 안도감이 듭니다. 구석에 있는 작은 개구멍이 눈에 띕니다."
            ],
            state_delta={
                "vars": {"location": "player_room"}
            }
        )

    # 3. 개구멍 탈출 (Escape)
    elif "개구멍" in user_input:
        return ToolResult(
            event_description=[
                 "이것은 테스트임다"
            ],
            state_delta={
                "flags": {"escaped_via_doghole": True},
                "locks": {"real_world": False}
            }
        )

    # Default Mock (Fallback)
    return ToolResult(
        event_description=[
            "플레이어가 새엄마에게 말을 걸었습니다.",
            "새엄마는 경계하는 눈빛을 보였습니다."
        ],
        state_delta={
            "npc_stats": {
                "mother": {
                    "trust": -10
                }
            },
            "flags": {
                "met_mother": True
            },
            "inventory_add": [],
            "inventory_remove": [],
            "locks": {},
            "vars": {},
            "turn_increment": 1,
            "memory_updates": {
                "mother": {
                    "last_interaction": "플레이어가 새엄마에게 말을 걸었습니다."
                }
            }
        }
    )