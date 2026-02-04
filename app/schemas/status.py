from enum import Enum


class NPCStatus(str, Enum):
    """NPC 상태"""
   # 생존 여부를 판단하는 상태
    ALIVE = "alive"      # 생존
    DECEASED = "deceased"  # 사망
    MISSING = "missing"    # 실종
    UNKNOWN = "unknown"    # 알 수 없음