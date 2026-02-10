from enum import Enum


class NPCStatus(str, Enum):
    """NPC 상태"""
   # 생존 여부를 판단하는 상태
    ALIVE = "alive"      # 생존
    DECEASED = "deceased"  # 사망
    MISSING = "missing"    # 실종
    UNKNOWN = "unknown"    # 알 수 없음

class ChatAt(str, Enum):
    """채팅 턴"""
    DAY = "day"
    NIGHT = "night"

class GameStatus(str, Enum):
    """게임 상태"""
    LIVE = "live"        # 진행 중
    ENDING = "ending"    # 종료됨

class ItemStatus(str, Enum):
    """아이템 상태"""
    FINE = "fine"        # 정상
    BURNED = "burned"    # 불가