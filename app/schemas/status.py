"""
app/schemas/status.py
모든 Enum 정의 통합
"""
from enum import Enum


class NPCStatus(str, Enum):
    """NPC 상태"""
    ALIVE = "alive"
    DECEASED = "deceased"
    MISSING = "missing"
    UNKNOWN = "unknown"
    SLEEPING = "sleeping"


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
    LIVE = "live"
    ENDING = "ending"


class Intent(str, Enum):
    """파싱된 의도 타입"""
    LEADING = "leading"
    NEUTRAL = "neutral"
    EMPATHIC = "empathic"
    SUMMARIZE = "summarize"
    UNKNOWN = "unknown"


class ToolName(str, Enum):
    """사용 가능한 Tool 이름"""
    NPC_TALK = "npc_talk"
    ACTION = "action"
    ITEM_USAGE = "item_usage"


class NpcId(str, Enum):
    """NPC 식별자"""
    STEPMOTHER = "stepmother"
    STEPFATHER = "stepfather"
    BROTHER = "brother"
    DOG = "dog"
    GRANDMOTHER = "grandmother"

