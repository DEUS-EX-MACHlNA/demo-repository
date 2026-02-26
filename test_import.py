import sys
print("Starting imports...")

try:
    print("Importing os...")
    import os
    print("Importing time...")
    import time
    print("Importing unittest.mock...")
    from unittest.mock import patch
    print("Importing SessionLocal...")
    from app.database import SessionLocal
    print("Importing GameService...")
    from app.services.game import GameService
    print("Importing crud_game...")
    from app.crud import game as crud_game
    print("Importing redis_client...")
    from app.redis_client import get_redis_client
    print("All imports SUCCESSFUL")
except Exception as e:
    print(f"Error: {e}")
